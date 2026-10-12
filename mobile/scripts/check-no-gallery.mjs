// Acceptance check (brief §14): "Gallery images cannot be submitted from the mobile app."
//
// The app enforces this by never including a way to pick existing photos: no image
// picker, media library or document picker package, and no source file importing one.
// This script fails `npm test` if that ever changes. (The API independently refuses any
// upload not marked capture_source=in_app_camera; device attestation will harden it.)

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const FORBIDDEN = [
  "expo-image-picker", "expo-media-library", "expo-document-picker",
  "react-native-image-picker", "react-native-image-crop-picker", "@react-native-camera-roll/camera-roll",
];

const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url)));
const deps = { ...pkg.dependencies, ...pkg.devDependencies };
const problems = FORBIDDEN.filter((name) => name in deps).map((n) => `package.json depends on ${n}`);

function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) walk(path);
    else if (/\.(tsx?|jsx?)$/.test(entry)) {
      const src = readFileSync(path, "utf8");
      for (const name of FORBIDDEN) if (src.includes(`"${name}`) || src.includes(`'${name}`)) problems.push(`${path} imports ${name}`);
      if (/type=["']file["']/.test(src)) problems.push(`${path} uses a file input`);
    }
  }
}
walk(new URL("../src", import.meta.url).pathname);

// The report upload must always declare the in-app camera.
const report = readFileSync(new URL("../src/app/(tabs)/index.tsx", import.meta.url), "utf8");
if (!report.includes('form.append("capture_source", "in_app_camera")')) problems.push("report upload no longer declares in_app_camera");

if (problems.length) {
  console.error("Gallery-upload check FAILED:\n  " + problems.join("\n  "));
  process.exit(1);
}
console.log("Gallery-upload check passed: no gallery/media picker anywhere in the app.");
