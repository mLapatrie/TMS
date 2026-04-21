// TMS controller for Arduino UNO R4 Minima (Renesas RA4M1)
// Rewritten from AVR. Uses micros()-polling instead of Timer1 ISR.

#include <Arduino.h>
#include <string.h>

// ===== Pin map =====
static const uint8_t VCC_PINS[]      = {11, 12, 13}; // always-HIGH 5V rails
static const uint8_t COMPARATOR_STOP = 2;            // HW overvolt trip status
static const uint8_t FIRE_CTRL       = 3;            // SCR gate pulse
static const uint8_t CHARGE_CTRL     = 4;            // HIGH = charge
static const uint8_t CAP_VOLTAGE     = A0;           // 0-5 V from divider

// Polarity of COMPARATOR_STOP. LOW = tripped.
#define COMP_STOP_ACTIVE LOW

// ===== Firmware overvoltage backup =====
// PLACEHOLDER. 10-bit ADC count. Set from divider ratio and target bus voltage.
// Example: 100:1 divider, trip at 300 V bus -> 3.00 V at A0 -> 614 counts.
static const uint16_t MAX_ADC = 800;

// ===== Timing =====
static const uint32_t SAMPLE_PERIOD_US = 1000;  // 1 kHz ADC sampling
static const uint32_t TELEM_PERIOD_MS  = 100;   // 10 Hz telemetry to host

// ===== Fire pulse =====
// Target at the SCR gate: 5 us. Measured digitalWrite overhead on R4 adds ~2 us
// on each side, so software delay of 3 us yields ~5 us at the pin. Verified on scope.
static const uint32_t FIRE_DELAY_US = 3;

// ===== State =====
volatile bool comp_stop_tripped = false;  // written from ISR

bool     charge_ok = false;   // false until RESET
bool     armed     = false;
bool     charging  = false;

uint16_t adc_last      = 0;
uint32_t t_last_ms     = 0;
uint32_t next_sample_us = 0;
uint32_t next_telem_ms  = 0;

// ===== Helpers =====
static void rails_up() {
  for (uint8_t i = 0; i < sizeof(VCC_PINS); i++) {
    pinMode(VCC_PINS[i], OUTPUT);
    digitalWrite(VCC_PINS[i], HIGH);
  }
}

static void safe_outputs() {
  digitalWrite(CHARGE_CTRL, LOW);
  digitalWrite(FIRE_CTRL, LOW);
  armed     = false;
  charge_ok = false;
  charging  = false;
}

static void fire_once() {
  // Mask IRQ so the comparator ISR cannot preempt mid-pulse and stretch it.
  noInterrupts();
  digitalWrite(FIRE_CTRL, HIGH);
  delayMicroseconds(FIRE_DELAY_US);
  digitalWrite(FIRE_CTRL, LOW);
  interrupts();
}

// ===== ISR for hardware comparator stop =====
static void comp_stop_isr() {
  // Drop charge signal as fast as possible, latch flag for loop().
  digitalWrite(CHARGE_CTRL, LOW);
  comp_stop_tripped = true;
}

// ===== Serial command handler =====
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
    charging  = false;
    //charge_ok = false;
    Serial.println("UNCHARGED");
  }
  else if (strcmp(cmd, "ARM") == 0) {
    digitalWrite(CHARGE_CTRL, LOW);
    charging  = false;
    charge_ok = false;
    armed     = true;
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
             charge_ok, armed, charging, comp_stop_tripped, adc_last);
    Serial.println(buf);
  }
  else {
    Serial.print("UNKNOWN:");
    Serial.println(cmd);
  }
}

// ===== Arduino entry points =====
void setup() {
  pinMode(CHARGE_CTRL, OUTPUT);
  pinMode(FIRE_CTRL, OUTPUT);
  pinMode(COMPARATOR_STOP, INPUT);  // external pull or comparator push-pull required
  pinMode(CAP_VOLTAGE, INPUT);
  safe_outputs();
  rails_up();

  // Register pre-existing hardware trip state at boot.
  if (digitalRead(COMPARATOR_STOP) == COMP_STOP_ACTIVE) {
    comp_stop_tripped = true;
  }

  attachInterrupt(digitalPinToInterrupt(COMPARATOR_STOP),
                  comp_stop_isr,
                  COMP_STOP_ACTIVE == HIGH ? RISING : FALLING);

  Serial.begin(115200);
  // Do not block on Serial. The R4 USB-CDC can be absent on bench power.
  Serial.println("BOOT");
}

void loop() {
  const uint32_t now_us = micros();
  const uint32_t now_ms = millis();

  // --- 1 kHz ADC sample ---
  if ((int32_t)(now_us - next_sample_us) >= 0) {
    next_sample_us = now_us + SAMPLE_PERIOD_US;
    adc_last  = analogRead(CAP_VOLTAGE);
    t_last_ms = now_ms;

    if (adc_last > MAX_ADC) {
      digitalWrite(CHARGE_CTRL, LOW);
      if (charge_ok || charging) {
        charge_ok = false;
        charging  = false;
        Serial.println("OVERVOLT");
      }
    }
  }

  // --- Hardware comparator trip latched in ISR, handled here ---
  if (comp_stop_tripped) {
    if (charge_ok || charging) {
      digitalWrite(CHARGE_CTRL, LOW);
      charge_ok = false;
      charging  = false;
      Serial.println("HW_STOP_TRIPPED");
    }
  }

  // --- 10 Hz telemetry ---
  if ((int32_t)(now_ms - next_telem_ms) >= 0) {
    next_telem_ms = now_ms + TELEM_PERIOD_MS;
    char buf[96];
    snprintf(buf, sizeof(buf),
             "T t=%lu adc=%u ok=%d arm=%d chg=%d hw=%d",
             t_last_ms, adc_last,
             charge_ok, armed, charging, comp_stop_tripped);
    Serial.println(buf);
  }

  // --- Command parser ---
  if (Serial.available()) {
    static char cmd[16];
    size_t n = Serial.readBytesUntil('\n', cmd, sizeof(cmd) - 1);
    cmd[n] = '\0';
    while (n > 0 && (cmd[n-1] == '\r' || cmd[n-1] == ' ')) cmd[--n] = '\0';
    if (n > 0) handle_command(cmd);
  }
}