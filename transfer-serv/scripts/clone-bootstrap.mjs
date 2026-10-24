import { mkdir, copyFile } from "node:fs/promises";

const destination = "frontend/public/assets/vendor/bootstrap";

await mkdir(destination, { recursive: true });

for (const file of [
  "css/bootstrap.min.css",
  "js/bootstrap.bundle.min.js"
]) {
  const filename = file.split("/").pop();

  await copyFile(
    `node_modules/bootstrap/dist/${file}`,
    `${destination}/${filename}`
  );
}

console.log("Bootstrap assets copied.");