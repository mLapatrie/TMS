// SPDX-License-Identifier: MIT
//
// TMS controller firmware for the Arduino UNO R4 Minima (Renesas RA4M1).
//
// This firmware controls high-voltage equipment. It is not a substitute for
// independent hardware interlocks, over-voltage protection, or safe operating
// procedures.

#include <Arduino.h>
#include <string.h>

// BEFORE STARTING -----------------------------------------------------------
// 1. Calculate MAX_ADC from measured values:
//
//       MAX_ADC = round((V_trip / divider_ratio) / V_ref * ADC_FULL_SCALE)
//
//    Example only: round(300 V / 100 / 5 V * 1023) = 614 counts.
// 2. Measure the SCR gate pulse on the assembled controller and adjust
//    FIRE_DELAY_US if the pulse width is not the required value.
// ---------------------------------------------------------------------------
static const uint8_t VCC_PINS[]      = {11, 12, 13};
static const uint8_t COMPARATOR_STOP = 2;
static const uint8_t FIRE_CTRL       = 3;
static const uint8_t CHARGE_CTRL     = 4;
static const uint8_t CAP_VOLTAGE     = A0;

// Comparator input configuration and active state
#define COMP_STOP_PIN_MODE INPUT
#define COMP_STOP_ACTIVE LOW

// ADC configuration. DEFAULT_MAX_ADC in app.py must match MAX_ADC.
static const uint8_t ADC_RESOLUTION_BITS = 10;
static const uint16_t ADC_FULL_SCALE = (1U << ADC_RESOLUTION_BITS) - 1U;
static const uint16_t MAX_ADC = 614;
static_assert(MAX_ADC <= ADC_FULL_SCALE,
              "MAX_ADC must be within the configured ADC range");

// Sampling and telemetry timing.
static const uint32_t SAMPLE_PERIOD_US = 1000;  // 1 kHz ADC sampling.
static const uint32_t TELEM_PERIOD_MS  = 100;   // 10 Hz host telemetry.

// Existing calibrated delay for an approximately 5 us SCR gate pulse.
// Re-measure on the final hardware; GPIO overhead depends on the board/core.
static const uint32_t FIRE_DELAY_US = 3;

// State shared with the comparator interrupt.
volatile bool comp_stop_tripped = false;

// Command-state flags. RESET is required before charging.
bool charge_ok = false;
bool armed = false;
bool charging = false;

uint16_t adc_last = 0;
uint32_t t_last_ms = 0;
uint32_t next_sample_us = 0;
uint32_t next_telem_ms = 0;

// Configure the three outputs that the existing hardware uses as logic-HIGH
// sources. Do not connect loads that exceed the board's GPIO ratings.
static void rails_up() {
  const size_t pin_count = sizeof(VCC_PINS) / sizeof(VCC_PINS[0]);
  for (size_t i = 0; i < pin_count; i++) {
    pinMode(VCC_PINS[i], OUTPUT);
    digitalWrite(VCC_PINS[i], HIGH);
  }
}

// Return command-controlled outputs and state flags to the inactive state.
static void safe_outputs() {
  digitalWrite(CHARGE_CTRL, LOW);
  digitalWrite(FIRE_CTRL, LOW);
  armed = false;
  charge_ok = false;
  charging = false;
}

static void fire_once() {
  // Prevent an interrupt from stretching the calibrated gate pulse.
  noInterrupts();
  digitalWrite(FIRE_CTRL, HIGH);
  delayMicroseconds(FIRE_DELAY_US);
  digitalWrite(FIRE_CTRL, LOW);
  interrupts();
}

static void comp_stop_isr() {
  // Disable charging immediately; loop() performs the non-ISR bookkeeping.
  digitalWrite(CHARGE_CTRL, LOW);
  comp_stop_tripped = true;
}

// Handle the newline-terminated ASCII command protocol used by app.py.
static void handle_command(const char *cmd) {
  if (strcmp(cmd, "RESET") == 0) {
    safe_outputs();
    if (digitalRead(COMPARATOR_STOP) != COMP_STOP_ACTIVE) {
      comp_stop_tripped = false;
      charge_ok = true;
      Serial.println("RESET_OK");
    } else {
      Serial.println("RESET_BLOCKED_HW_TRIP");
    }
  }
  else if (strcmp(cmd, "CHARGE") == 0) {
    if (charge_ok && !armed && !comp_stop_tripped) {
      digitalWrite(CHARGE_CTRL, HIGH);
      charging = true;
      Serial.println("CHARGING");
    } else {
      Serial.println("CHARGE_DENIED");
    }
  }
  else if (strcmp(cmd, "UNCHARGE") == 0) {
    digitalWrite(CHARGE_CTRL, LOW);
    charging = false;
    Serial.println("UNCHARGED");
  }
  else if (strcmp(cmd, "ARM") == 0) {
    digitalWrite(CHARGE_CTRL, LOW);
    charging = false;
    charge_ok = false;
    armed = true;
    Serial.println("ARMED");
  }
  else if (strcmp(cmd, "UNARM") == 0) {
    armed = false;
    Serial.println("UNARMED");
  }
  else if (strcmp(cmd, "FIRE") == 0) {
    if (armed && !charge_ok && !comp_stop_tripped) {
      fire_once();
      armed = false;
      Serial.println("FIRED");
    } else {
      Serial.println("FIRE_DENIED");
    }
  }
  else if (strcmp(cmd, "STATUS") == 0) {
    char buf[96];
    snprintf(buf, sizeof(buf),
             "STATUS ok=%d arm=%d chg=%d hw=%d adc=%u",
             charge_ok, armed, charging, comp_stop_tripped,
             static_cast<unsigned int>(adc_last));
    Serial.println(buf);
  }
  else {
    Serial.print("UNKNOWN:");
    Serial.println(cmd);
  }
}

void setup() {
  pinMode(CHARGE_CTRL, OUTPUT);
  pinMode(FIRE_CTRL, OUTPUT);
  pinMode(COMPARATOR_STOP, COMP_STOP_PIN_MODE);
  pinMode(CAP_VOLTAGE, INPUT);
  analogReadResolution(ADC_RESOLUTION_BITS);

  safe_outputs();
  rails_up();

  // Latch a comparator trip that is already active at startup.
  if (digitalRead(COMPARATOR_STOP) == COMP_STOP_ACTIVE) {
    comp_stop_tripped = true;
  }

  attachInterrupt(digitalPinToInterrupt(COMPARATOR_STOP),
                  comp_stop_isr,
                  COMP_STOP_ACTIVE == HIGH ? RISING : FALLING);

  Serial.begin(115200);
  // Do not wait for a host connection; the controller may run from bench power.
  Serial.println("BOOT");
}

void loop() {
  const uint32_t now_us = micros();
  const uint32_t now_ms = millis();

  // Sample the capacitor-voltage monitor at approximately 1 kHz.
  if ((int32_t)(now_us - next_sample_us) >= 0) {
    next_sample_us = now_us + SAMPLE_PERIOD_US;
    adc_last = analogRead(CAP_VOLTAGE);
    t_last_ms = now_ms;

    if (adc_last > MAX_ADC) {
      digitalWrite(CHARGE_CTRL, LOW);
      if (charge_ok || charging) {
        charge_ok = false;
        charging = false;
        Serial.println("OVERVOLT");
      }
    }
  }

  // Complete handling of a hardware comparator trip latched by the ISR.
  if (comp_stop_tripped) {
    if (charge_ok || charging) {
      digitalWrite(CHARGE_CTRL, LOW);
      charge_ok = false;
      charging = false;
      Serial.println("HW_STOP_TRIPPED");
    }
  }

  // Report controller state to the host at approximately 10 Hz.
  if ((int32_t)(now_ms - next_telem_ms) >= 0) {
    next_telem_ms = now_ms + TELEM_PERIOD_MS;
    char buf[96];
    snprintf(buf, sizeof(buf),
             "T t=%lu adc=%u ok=%d arm=%d chg=%d hw=%d",
             static_cast<unsigned long>(t_last_ms),
             static_cast<unsigned int>(adc_last),
             charge_ok, armed, charging, comp_stop_tripped);
    Serial.println(buf);
  }

  // Read one newline-terminated command. Commands are at most 15 characters.
  if (Serial.available()) {
    static char cmd[16];
    size_t n = Serial.readBytesUntil('\n', cmd, sizeof(cmd) - 1);
    cmd[n] = '\0';
    while (n > 0 && (cmd[n-1] == '\r' || cmd[n-1] == ' ')) cmd[--n] = '\0';
    if (n > 0) handle_command(cmd);
  }
}
