#include <avr/io.h>
#include <avr/interrupt.h>

// pin definitions 
int count=0;

const int CHARGE_CTRL = 17; 
const int FIRE_CTRL = 15;
const int COMPARATOR_STOP = 2; //19 on sheet
const int CAP_VOLTAGE = A0;
const int MAX_VOLTAGE = 255; //replace later

// interrupt variables
volatile bool charge_ok = true;
volatile bool arm_on = false;
volatile int voltage;
volatile unsigned long time;
volatile bool send_ready;

void setup() {
  //ADD RESET
  // put your setup code here, to run once:
  pinMode(CHARGE_CTRL, OUTPUT);
  pinMode(FIRE_CTRL, OUTPUT); //READY SIGNAL
  pinMode(COMPARATOR_STOP, INPUT); // where we read READY
  pinMode(CAP_VOLTAGE, INPUT); //ERROR INPUT

  attachInterrupt(digitalPinToInterrupt(COMPARATOR_STOP), error, RISING); // ISR called when error goes from 0 -> 1

  // SETTING UP VOLTAGE READING INTERRUPT
  noInterrupts();
  TCCR1A = 0;
  TCCR1B = 0;
  TCNT1  = 0;

  OCR1A = (F_CPU / 1024) - 1;

  TCCR1B |= (1 << WGM12);               // CTC mode
  TCCR1B |= (1 << CS12) | (1 << CS10);  // prescaler 1024
  TIMSK1 |= (1 << OCIE1A);

  interrupts();

  Serial.begin(115200);
}

void loop() {
  // put your main code here, to run repeatedly:
  
  if (voltage>MAX_VOLTAGE){
      charge_ok=false;
      digitalWrite(CHARGE_CTRL, LOW);
      Serial.println("MAXIMUM VOLTAGE REACHED");
  }

  if (Serial.available()){
    String cmd = Serial.readStringUntil('\n');
    if (cmd=="CHARGE" && charge_ok){
      digitalWrite(CHARGE_CTRL, HIGH);
      Serial.println("CHARGING");
    }
    if (cmd=="ARM"){
      arm_on=true;
      charge_ok=false;
      digitalWrite(CHARGE_CTRL, LOW);
      Serial.println("ARMED");
    }
    if (cmd=="UNARM"){
      arm_on=false;
      Serial.println("UNARMED");
    }

    if (cmd=="FIRE" && !charge_ok && arm_on){
  
      digitalWrite(FIRE_CTRL, HIGH);
      delayMicroseconds(3);
      digitalWrite(FIRE_CTRL, LOW);
      Serial.println("ARMED");
    }

    if (cmd=="UNCHARGE"){
      charge_ok=false;
      digitalWrite(CHARGE_CTRL, LOW);
      Serial.println("UNCHARGING");
    }
  }

  if (send_ready){
    char buf[48];
    snprintf(buf, sizeof(buf), "time: %lu, adc_voltage: %d", time, voltage);
    Serial.println(buf);
    send_ready=false;
  } 
}


ISR(TIMER1_COMPA_vect) {
  voltage=analogRead(CAP_VOLTAGE);
  time=millis();
  send_ready=true;
}

void error(){
  charge_ok=false;
  digitalWrite(CHARGE_CTRL, LOW);
  Serial.println("ERROR");
}
