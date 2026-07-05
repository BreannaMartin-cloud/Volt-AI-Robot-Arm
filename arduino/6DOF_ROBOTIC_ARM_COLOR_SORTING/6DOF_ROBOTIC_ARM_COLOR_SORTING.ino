#include <Servo.h>

// ---------------------------------------------------------------------------
// VOLT - 6DOF color-sorting sketch
//
// Safety note: hobby servos have no position feedback. The instant a servo
// is attached/powered it drives at full speed toward whatever angle it's
// told, regardless of where it's actually resting. This sketch waits for you
// to type ARM over Serial before it attaches any servo or moves anything, so
// you have a chance to clear the area and support the arm first - especially
// the elbow (servoELBOW), which is what the whole forearm/wrist/gripper
// hangs from when the arm is folded at rest.
// ---------------------------------------------------------------------------

Servo servoWAIST, servoSHOULDER, servoELBOW, servoWRISTPITCH, servoWRISTROLL, servoGRIPPER;
int posWAIST = 90, posSHOULDER = 90, posELBOW = 90;
int posPITCH = 90, posROLL = 90, posGRIPPER = 90;

const int PIN_WAIST = 3, PIN_SHOULDER = 5, PIN_ELBOW = 6;
const int PIN_PITCH = 9, PIN_ROLL = 10, PIN_GRIPPER = 11;

// ------------ COLOR SENSOR PINS (TCS3200) ------------
const int s0 = 12;
const int s1 = 13;
const int s2 = 7;
const int s3 = 8;
const int out = 4;

// pulseIn() has no bound by default and will happily hang for its full
// timeout (or, if you pass 0, forever) if the sensor is miswired or a wire
// comes loose mid-run. Give it a hard ceiling so a bad reading just comes
// back as 0 instead of freezing the whole arm mid-motion.
const unsigned long COLOR_PULSE_TIMEOUT_US = 25000UL;  // 25ms

// ------------ COLOR READINGS ------------
int redVal = 0, greenVal = 0, blueVal = 0;

bool armed = false;
String inputString = "";
bool stringComplete = false;

void setup() {
  Serial.begin(9600);
  inputString.reserve(20);

  pinMode(s0, OUTPUT);
  pinMode(s1, OUTPUT);
  digitalWrite(s0, HIGH);  // 20% frequency scaling
  digitalWrite(s1, LOW);

  pinMode(s2, OUTPUT);
  pinMode(s3, OUTPUT);
  pinMode(out, INPUT);

  Serial.println();
  Serial.println(F("=================================================="));
  Serial.println(F("VOLT color sorter - SAFE BOOT"));
  Serial.println(F("Servos are NOT attached yet - no signal, no movement."));
  Serial.println(F("If the arm is resting folded at the elbow with the"));
  Serial.println(F("claw down on the table, that's expected while off."));
  Serial.println(F("Clear the area and the color sensor's view, be ready"));
  Serial.println(F("to support the arm, then type ARM and press Enter."));
  Serial.println(F("=================================================="));
}

void loop() {
  if (!armed) {
    checkForArmCommand();
    return;
  }

  readColor();

  Serial.print("R: "); Serial.print(redVal);
  Serial.print(" | G: "); Serial.print(greenVal);
  Serial.print(" | B: "); Serial.println(blueVal);

  if (isRed()) {
    Serial.println("Detected RED box");
    redTask();
  } else if (isGreen()) {
    Serial.println("Detected GREEN box");
    greenTask();
  } else if (isBlue()) {
    Serial.println("Detected BLUE box");
    blueTask();
  } else {
    Serial.println("No valid color detected.");
  }

  delay(2000);
}

void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '\n' || inChar == '\r') {
      if (inputString.length() > 0) stringComplete = true;
    } else {
      inputString += inChar;
    }
  }
}

void checkForArmCommand() {
  if (!stringComplete) return;
  inputString.trim();
  inputString.toUpperCase();
  if (inputString == "ARM") {
    Serial.println(F("Arming - attaching servos now..."));
    servoWAIST.attach(PIN_WAIST);
    servoSHOULDER.attach(PIN_SHOULDER);
    servoELBOW.attach(PIN_ELBOW);
    servoWRISTPITCH.attach(PIN_PITCH);
    servoWRISTROLL.attach(PIN_ROLL);
    servoGRIPPER.attach(PIN_GRIPPER);
    armed = true;

    // Slow first move only - see moveSmooth's stepDelayMs parameter.
    Serial.println(F("Homing slowly..."));
    moveArm(94, 90, 70, 100, 100, 120, 25);
    delay(2000);
    Serial.println(F("Armed and homed. Starting color sort loop."));
  } else {
    Serial.println(F("Type ARM to continue."));
  }
  inputString = "";
  stringComplete = false;
}

// ------------ COLOR SENSOR FUNCTIONS ------------

void readColor() {
  redVal = readColorValue(LOW, LOW);        // Red filter
  greenVal = readColorValue(HIGH, HIGH);    // Green filter
  blueVal = readColorValue(LOW, HIGH);      // Blue filter
}

int readColorValue(bool s2val, bool s3val) {
  digitalWrite(s2, s2val);
  digitalWrite(s3, s3val);
  delay(50);
  unsigned long pulse = pulseIn(out, LOW, COLOR_PULSE_TIMEOUT_US);
  return (int)pulse;  // 0 if the sensor didn't respond in time
}

bool isRed() {
  return (redVal > 0 && redVal < greenVal && redVal < blueVal && redVal < 60);
}

bool isGreen() {
  return (greenVal > 0 && greenVal < redVal && greenVal < blueVal && greenVal < 60);
}

bool isBlue() {
  return (blueVal > 0 && blueVal < redVal && blueVal < greenVal && blueVal < 90);
}

// ------------ SERVO MOVEMENT FUNCTIONS ------------

void moveSmooth(Servo &servo, int &currentPos, int targetPos, int stepDelayMs) {
  targetPos = constrain(targetPos, 0, 180);
  int step = (targetPos > currentPos) ? 1 : -1;
  for (int pos = currentPos; pos != targetPos; pos += step) {
    servo.write(pos);
    delay(stepDelayMs);
  }
  currentPos = targetPos;
  servo.write(currentPos);
}

void moveArm(int waist, int shoulder, int elbow, int pitch, int roll, int gripper) {
  moveArm(waist, shoulder, elbow, pitch, roll, gripper, 10);
}

void moveArm(int waist, int shoulder, int elbow, int pitch, int roll, int gripper, int stepDelayMs) {
  moveSmooth(servoWAIST, posWAIST, waist, stepDelayMs);
  moveSmooth(servoSHOULDER, posSHOULDER, shoulder, stepDelayMs);
  moveSmooth(servoELBOW, posELBOW, elbow, stepDelayMs);
  moveSmooth(servoWRISTPITCH, posPITCH, pitch, stepDelayMs);
  moveSmooth(servoWRISTROLL, posROLL, roll, stepDelayMs);
  moveSmooth(servoGRIPPER, posGRIPPER, gripper, stepDelayMs);
}

// ------------ PICK-AND-PLACE TASKS ------------

void redTask() {
  gripperCheck();
  moveArm(94, 90, 70, 100, 100, 50);
  moveArm(94, 95, 70, 55, 100, 95);
  moveArm(94, 95, 60, 55, 100, 95);
  moveArm(175, 90, 60, 120, 180, 95);
  moveArm(175, 80, 65, 100, 180, 50);
  moveArm(175, 80, 50, 100, 180, 50);
  moveArm(94, 90, 70, 100, 100, 120);
}

void greenTask() {
  gripperCheck();
  moveArm(94, 90, 70, 100, 100, 50);
  moveArm(94, 95, 70, 55, 100, 95);
  moveArm(94, 95, 60, 55, 100, 95);
  moveArm(94, 90, 60, 80, 100, 95);
  moveArm(180, 90, 65, 55, 180, 50);
  moveArm(180, 90, 65, 55, 100, 50);
  moveArm(180, 90, 65, 100, 100, 50);
  moveArm(94, 90, 70, 100, 100, 120);
}

void blueTask() {
  gripperCheck();
  moveArm(94, 90, 70, 100, 100, 50);
  moveArm(94, 95, 70, 55, 100, 95);
  moveArm(94, 95, 60, 55, 100, 95);
  moveArm(140, 110, 60, 80, 135, 95);
  moveArm(140, 80, 60, 80, 135, 95);
  moveArm(140, 80, 60, 80, 135, 50);
  moveArm(140, 90, 60, 100, 180, 50);
  moveArm(94, 90, 70, 100, 100, 120);
}

// ------------ GRIPPER TEST FUNCTION ------------

void gripperCheck() {
  servoGRIPPER.write(50); delay(300);
  servoGRIPPER.write(120); delay(300);
  servoGRIPPER.write(50); delay(300);
  servoGRIPPER.write(120); delay(300);
  posGRIPPER = 120;
}
