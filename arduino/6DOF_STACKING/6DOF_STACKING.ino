#include <Servo.h>  // Include the Servo library

// ---------------------------------------------------------------------------
// VOLT - 6DOF stacking sketch
//
// Safety note: hobby servos have no position feedback. The instant a servo
// is attached/powered it drives at full speed toward whatever angle it's
// told, regardless of where it's actually resting. This sketch waits for you
// to type ARM over Serial before it attaches any servo or moves anything, so
// you have a chance to clear the area and support the arm first - especially
// the elbow servo, which is what the whole forearm/wrist/gripper hangs from
// when the arm is folded at rest.
// ---------------------------------------------------------------------------

// Servo objects
Servo baseServo;
Servo shoulderServo;
Servo elbowServo;
Servo wristPitchServo;
Servo wristRollServo;
Servo gripperServo;

// Pin assignments
const int BASE_PIN = 3;
const int SHOULDER_PIN = 5;
const int ELBOW_PIN = 6;
const int WRIST_PITCH_PIN = 9;
const int WRIST_ROLL_PIN = 10;
const int GRIPPER_PIN = 11;

// Current servo positions
int basePos = 90;
int shoulderPos = 90;
int elbowPos = 90;
int wristPitchPos = 90;
int wristRollPos = 90;
int gripperPos = 90;

bool armed = false;
String inputString = "";
bool stringComplete = false;

// Smoothly move a single servo
void smoothServoMove(Servo& servo, int& currentPos, int targetPos, int stepDelayMs) {
  int step = (currentPos < targetPos) ? 1 : -1;
  while (currentPos != targetPos) {
    currentPos += step;
    servo.write(currentPos);
    delay(stepDelayMs);
  }
}

// Smooth simultaneous movement for all joints
void moveArmSmooth(int base, int shoulder, int elbow, int wristPitch, int wristRoll, int gripper, int stepDelayMs) {
  // Clamp within 0-180 range
  base = constrain(base, 0, 180);
  shoulder = constrain(shoulder, 0, 180);
  elbow = constrain(elbow, 0, 180);
  wristPitch = constrain(wristPitch, 0, 180);
  wristRoll = constrain(wristRoll, 0, 180);
  gripper = constrain(gripper, 0, 180);

  // Move each servo smoothly
  smoothServoMove(baseServo, basePos, base, stepDelayMs);
  smoothServoMove(shoulderServo, shoulderPos, shoulder, stepDelayMs);
  smoothServoMove(elbowServo, elbowPos, elbow, stepDelayMs);
  smoothServoMove(wristPitchServo, wristPitchPos, wristPitch, stepDelayMs);
  smoothServoMove(wristRollServo, wristRollPos, wristRoll, stepDelayMs);
  smoothServoMove(gripperServo, gripperPos, gripper, stepDelayMs);
}

void moveArmSmooth(int base, int shoulder, int elbow, int wristPitch, int wristRoll, int gripper) {
  moveArmSmooth(base, shoulder, elbow, wristPitch, wristRoll, gripper, 10);
}

void setup() {
  Serial.begin(9600);
  inputString.reserve(20);

  Serial.println();
  Serial.println(F("=================================================="));
  Serial.println(F("VOLT stacking - SAFE BOOT"));
  Serial.println(F("Servos are NOT attached yet - no signal, no movement."));
  Serial.println(F("If the arm is resting folded at the elbow with the"));
  Serial.println(F("claw down on the table, that's expected while off."));
  Serial.println(F("Clear the stacking area, be ready to support the arm,"));
  Serial.println(F("then type ARM and press Enter to begin."));
  Serial.println(F("=================================================="));
}

void loop() {
  if (!armed) {
    checkForArmCommand();
    return;
  }

  runStackingRoutine();
  // while (true); // Stop after one pass instead of looping forever
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
    baseServo.attach(BASE_PIN);
    shoulderServo.attach(SHOULDER_PIN);
    elbowServo.attach(ELBOW_PIN);
    wristPitchServo.attach(WRIST_PITCH_PIN);
    wristRollServo.attach(WRIST_ROLL_PIN);
    gripperServo.attach(GRIPPER_PIN);
    armed = true;

    // Initial gripper position, then slow first move to the neutral pose.
    gripperServo.write(gripperPos);
    delay(500);
    Serial.println(F("Homing slowly..."));
    moveArmSmooth(90, 90, 65, 90, 90, 40, 25);
    delay(1000);
    Serial.println(F("Armed and homed. Starting stacking routine."));
  } else {
    Serial.println(F("Type ARM to continue."));
  }
  inputString = "";
  stringComplete = false;
}

void runStackingRoutine() {
  // === STACK 1 ===
  moveArmSmooth(90, 91, 76, 40, 90, 40); // Reach cube 1
  delay(500);
  moveArmSmooth(90, 91, 76, 40, 90, 85); // Grip
  delay(300);
  moveArmSmooth(90, 100, 76, 40, 90, 85); // Adjust shoulder
  moveArmSmooth(90, 90, 65, 85, 90, 85); // Lift
  moveArmSmooth(90, 73, 65, 64, 90, 85); // Slightly raised
  delay(300);
  moveArmSmooth(90, 73, 65, 64, 90, 40); // Release
  delay(300);
  moveArmSmooth(90, 90, 65, 85, 90, 40); // Reset
  delay(1000);

  // === STACK 2 ===
  moveArmSmooth(90, 91, 76, 40, 90, 40); // Reach cube 2
  delay(500);
  moveArmSmooth(90, 91, 76, 40, 90, 85); // Grip
  delay(300);
  moveArmSmooth(90, 100, 76, 40, 90, 85); // Adjust
  moveArmSmooth(90, 90, 65, 85, 90, 85); // Lift
  moveArmSmooth(90, 80, 66, 61, 90, 85); // Position
  delay(300);
  moveArmSmooth(90, 80, 66, 61, 90, 40); // Release
  delay(300);
  moveArmSmooth(90, 90, 65, 85, 90, 40); // Reset
  delay(1000);

  // === STACK 3 ===
  moveArmSmooth(90, 91, 76, 40, 90, 40); // Reach cube 3
  delay(500);
  moveArmSmooth(90, 91, 76, 40, 90, 85); // Grip
  delay(300);
  moveArmSmooth(90, 100, 76, 40, 90, 85); // Adjust
  moveArmSmooth(120, 100, 50, 85, 90, 85); // Side move
  moveArmSmooth(94, 100, 50, 85, 90, 85); // Lift
  moveArmSmooth(94, 93, 68, 61, 90, 85); // Higher
  delay(300);
  moveArmSmooth(94, 93, 68, 61, 90, 40); // Release
  delay(300);
  moveArmSmooth(90, 90, 65, 85, 90, 40); // Reset
  delay(1000);

  // === STATION 2: STACK 1 ===
  moveArmSmooth(90, 91, 76, 40, 90, 40);
  delay(500);
  moveArmSmooth(90, 91, 76, 40, 90, 85);
  delay(300);
  moveArmSmooth(90, 100, 76, 40, 90, 85);
  moveArmSmooth(65, 100, 76, 40, 90, 85);
  moveArmSmooth(65, 90, 65, 85, 90, 85);
  moveArmSmooth(63, 73, 65, 62, 54, 85);
  delay(300);
  moveArmSmooth(63, 73, 65, 64, 55, 40);
  delay(300);
  moveArmSmooth(63, 90, 65, 85, 90, 40);
  moveArmSmooth(90, 90, 65, 85, 90, 40);
  delay(1000);

  // === STACK 2 ===
  moveArmSmooth(90, 91, 76, 41, 90, 40);
  delay(500);
  moveArmSmooth(90, 91, 76, 41, 90, 85);
  delay(300);
  moveArmSmooth(90, 100, 76, 41, 90, 85);
  moveArmSmooth(63, 100, 76, 41, 90, 85);
  moveArmSmooth(63, 90, 65, 85, 90, 85);
  moveArmSmooth(63, 80, 67, 62, 55, 85);
  delay(300);
  moveArmSmooth(63, 76, 66, 62, 55, 40);
  delay(300);
  moveArmSmooth(63, 90, 65, 85, 90, 40);
  moveArmSmooth(90, 90, 65, 85, 90, 40);
  delay(1000);

  // === STACK 3 ===
  moveArmSmooth(90, 91, 76, 40, 90, 40);
  delay(500);
  moveArmSmooth(90, 91, 76, 40, 90, 85);
  delay(300);
  moveArmSmooth(90, 100, 76, 40, 90, 85);
  moveArmSmooth(63, 100, 76, 40, 90, 85);
  moveArmSmooth(45, 100, 50, 85, 90, 85);
  moveArmSmooth(63, 90, 65, 85, 50, 85);
  moveArmSmooth(63, 90, 65, 58, 52, 85);
  delay(300);
  moveArmSmooth(62, 90, 65, 58, 55, 40);
  delay(300);
  moveArmSmooth(63, 90, 65, 85, 90, 40);
  moveArmSmooth(90, 90, 65, 85, 90, 40);
  delay(1000);

  armed = false;  // require ARM again before another pass
  Serial.println(F("Routine complete. Type ARM to run it again."));
}
