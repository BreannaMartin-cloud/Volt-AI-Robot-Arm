#include <Servo.h>

// ---------------------------------------------------------------------------
// VOLT - 6DOF testing & calibration sketch
//
// Servos are NEVER attached automatically on boot. Hobby servos have no
// position feedback, so the moment a servo is attached/powered it will snap
// at full speed toward whatever angle it's told - it does not know, and this
// sketch cannot know, where the arm is physically resting. If a joint horn
// was installed a few (or many) degrees off from where "90" is in software,
// that first snap can be large and sudden - especially dangerous on the
// elbow (servoC), since that's the joint the whole forearm/wrist/gripper
// hangs from when the arm is folded at rest.
//
// So: on boot this sketch waits for you to type ARM before it attaches any
// servo. Use that pause to clear the area and be ready to support the arm.
// ---------------------------------------------------------------------------

Servo servoA;  // BASE
Servo servoB;  // SHOULDER
Servo servoC;  // ELBOW
Servo servoD;  // WRIST PITCH
Servo servoE;  // WRIST ROLL
Servo servoF;  // GRIPPER

const int PIN_A = 3, PIN_B = 5, PIN_C = 6, PIN_D = 9, PIN_E = 10, PIN_F = 11;

// Home pose, applied only after ARM + the slow first move below.
int angleA = 90;
int angleB = 90;
int angleC = 90;
int angleD = 90;
int angleE = 90;
int angleF = 90;

// Soft limits per joint. These are NOT the same as the servo's mechanical
// 0-180 range - they're the range you've confirmed is safe for THIS frame
// (won't crash into the base, the desk, or itself). Tighten these with the
// LIMIT command below once you've found the real safe range for your build.
// Defaults are conservative-ish placeholders, not verified for your frame.
int limitLoA = 0,   limitHiA = 180;  // base
int limitLoB = 20,  limitHiB = 160;  // shoulder
int limitLoC = 20,  limitHiC = 160;  // elbow
int limitLoD = 0,   limitHiD = 180;  // wrist pitch
int limitLoE = 0,   limitHiE = 180;  // wrist roll
int limitLoF = 30,  limitHiF = 150;  // gripper - don't let this drive past its mechanical stop

bool armed = false;

// Input buffer
String inputString = "";
bool stringComplete = false;

void setup() {
  Serial.begin(9600);
  inputString.reserve(50);

  Serial.println();
  Serial.println(F("=================================================="));
  Serial.println(F("VOLT arm - SAFE BOOT"));
  Serial.println(F("Servos are NOT attached yet - no signal, no movement."));
  Serial.println(F("If the arm is resting folded at the elbow with the"));
  Serial.println(F("claw down on the table, that's expected while off."));
  Serial.println(F("Clear the area, be ready to support the arm, then"));
  Serial.println(F("type ARM and press Enter to attach servos and home."));
  Serial.println(F("=================================================="));
}

void loop() {
  if (!stringComplete) return;

  if (!armed) {
    inputString.trim();
    inputString.toUpperCase();
    if (inputString == "ARM") {
      armServos();
    } else {
      Serial.println(F("Type ARM to continue."));
    }
    inputString = "";
    stringComplete = false;
    return;
  }

  processCommand(inputString);
  inputString = "";
  stringComplete = false;
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

void armServos() {
  Serial.println(F("Arming - attaching servos now..."));
  servoA.attach(PIN_A);
  servoB.attach(PIN_B);
  servoC.attach(PIN_C);
  servoD.attach(PIN_D);
  servoE.attach(PIN_E);
  servoF.attach(PIN_F);
  armed = true;

  // First move after attach is the one that matters most: go slowly, in
  // case the assumed starting angle doesn't match the true physical angle.
  Serial.println(F("Homing slowly..."));
  moveSmooth(servoA, angleA, 25);
  moveSmooth(servoB, angleB, 25);
  moveSmooth(servoC, angleC, 25);
  moveSmooth(servoD, angleD, 25);
  moveSmooth(servoE, angleE, 25);
  moveSmooth(servoF, angleF, 25);

  Serial.println(F("Armed and homed."));
  Serial.println(F("Enter commands like: A 90 B 120 C 60 D 70 E 90 F 50"));
  Serial.println(F("Or: LIMIT B 25 155   (set soft limits for a joint)"));
  Serial.println(F("Or: POSE             (print current angles)"));
  printPose();
}

void processCommand(String command) {
  command.trim();
  command.toUpperCase();

  if (command == "POSE") {
    printPose();
    return;
  }

  if (command.startsWith("LIMIT ")) {
    processLimitCommand(command);
    return;
  }

  command += " ";  // simplify parsing
  int index = 0;

  while (index < command.length()) {
    char servoChar = command.charAt(index);
    index++;

    while (index < command.length() && command.charAt(index) == ' ') index++;

    String angleStr = "";
    bool negative = false;
    if (index < command.length() && command.charAt(index) == '-') {
      negative = true;
      index++;
    }
    while (index < command.length() && isDigit(command.charAt(index))) {
      angleStr += command.charAt(index);
      index++;
    }

    if (angleStr.length() == 0) {
      if (servoChar != ' ') {
        Serial.print(F("No angle given for "));
        Serial.println(servoChar);
      }
      while (index < command.length() && command.charAt(index) == ' ') index++;
      continue;
    }

    int angle = angleStr.toInt();
    if (negative) angle = -angle;

    moveJoint(servoChar, angle);

    while (index < command.length() && command.charAt(index) == ' ') index++;
  }
}

void moveJoint(char servoChar, int angle) {
  switch (servoChar) {
    case 'A':
      angle = constrain(angle, limitLoA, limitHiA);
      moveSmooth(servoA, angle, 10);
      angleA = angle;
      Serial.print(F("A set to ")); Serial.println(angle);
      break;
    case 'B':
      angle = constrain(angle, limitLoB, limitHiB);
      moveSmooth(servoB, angle, 10);
      angleB = angle;
      Serial.print(F("B set to ")); Serial.println(angle);
      break;
    case 'C':
      angle = constrain(angle, limitLoC, limitHiC);
      moveSmooth(servoC, angle, 10);
      angleC = angle;
      Serial.print(F("C set to ")); Serial.println(angle);
      break;
    case 'D':
      angle = constrain(angle, limitLoD, limitHiD);
      moveSmooth(servoD, angle, 10);
      angleD = angle;
      Serial.print(F("D set to ")); Serial.println(angle);
      break;
    case 'E':
      angle = constrain(angle, limitLoE, limitHiE);
      moveSmooth(servoE, angle, 10);
      angleE = angle;
      Serial.print(F("E set to ")); Serial.println(angle);
      break;
    case 'F':
      angle = constrain(angle, limitLoF, limitHiF);
      moveSmooth(servoF, angle, 10);
      angleF = angle;
      Serial.print(F("F set to ")); Serial.println(angle);
      break;
    default:
      Serial.print(F("Invalid servo name: "));
      Serial.println(servoChar);
  }
}

// "LIMIT <A-F> <lo> <hi>" - narrow the safe travel range for one joint once
// you've found (by testing with small moves) where it actually collides
// with the frame or the desk.
void processLimitCommand(String command) {
  int firstSpace = command.indexOf(' ');
  String rest = command.substring(firstSpace + 1);
  rest.trim();

  int sp1 = rest.indexOf(' ');
  if (sp1 < 0) { Serial.println(F("Usage: LIMIT <A-F> <lo> <hi>")); return; }
  char servoChar = rest.charAt(0);
  String tail = rest.substring(sp1 + 1);
  tail.trim();
  int sp2 = tail.indexOf(' ');
  if (sp2 < 0) { Serial.println(F("Usage: LIMIT <A-F> <lo> <hi>")); return; }

  int lo = tail.substring(0, sp2).toInt();
  int hi = tail.substring(sp2 + 1).toInt();
  if (lo > hi) { Serial.println(F("lo must be <= hi")); return; }
  lo = constrain(lo, 0, 180);
  hi = constrain(hi, 0, 180);

  switch (servoChar) {
    case 'A': limitLoA = lo; limitHiA = hi; break;
    case 'B': limitLoB = lo; limitHiB = hi; break;
    case 'C': limitLoC = lo; limitHiC = hi; break;
    case 'D': limitLoD = lo; limitHiD = hi; break;
    case 'E': limitLoE = lo; limitHiE = hi; break;
    case 'F': limitLoF = lo; limitHiF = hi; break;
    default:
      Serial.print(F("Invalid servo name: "));
      Serial.println(servoChar);
      return;
  }
  Serial.print(F("Limits for ")); Serial.print(servoChar);
  Serial.print(F(": ")); Serial.print(lo); Serial.print(F(" - ")); Serial.println(hi);
}

void printPose() {
  Serial.print(F("A=")); Serial.print(angleA);
  Serial.print(F(" B=")); Serial.print(angleB);
  Serial.print(F(" C=")); Serial.print(angleC);
  Serial.print(F(" D=")); Serial.print(angleD);
  Serial.print(F(" E=")); Serial.print(angleE);
  Serial.print(F(" F=")); Serial.println(angleF);
}

// Smooth servo movement. Takes the servo by reference (a Servo object holds
// real state - passing by value silently copies it, which is easy to get
// wrong later if this function is ever extended to track more than the pin).
// stepDelayMs lets the initial home-after-ARM move go slower than routine
// moves.
void moveSmooth(Servo &servo, int targetAngle, int stepDelayMs) {
  targetAngle = constrain(targetAngle, 0, 180);
  int currentAngle = servo.read();
  if (currentAngle < targetAngle) {
    for (int i = currentAngle; i <= targetAngle; i++) {
      servo.write(i);
      delay(stepDelayMs);
    }
  } else {
    for (int i = currentAngle; i >= targetAngle; i--) {
      servo.write(i);
      delay(stepDelayMs);
    }
  }
}
