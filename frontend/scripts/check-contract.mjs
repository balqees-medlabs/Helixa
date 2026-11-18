import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, rmSync } from "node:fs";
import path from "node:path";
import process from "node:process";

const root = process.cwd();
const input = path.resolve(root, "../backend/openapi.json");
const committed = path.join(root, "lib/api/schema.d.ts");
const temporary = path.join(root, "lib/api/.schema.tmp.d.ts");
const binary = path.join(root, "node_modules/.bin/openapi-typescript");

if (!existsSync(input)) {
  console.error(`Missing backend contract: ${input}`);
  process.exit(1);
}
if (!existsSync(committed)) {
  console.error("Missing lib/api/schema.d.ts. Run `npm run gen:client` and commit the result.");
  process.exit(1);
}

try {
  execFileSync(binary, [input, "-o", temporary], { stdio: "inherit" });
  const expected = readFileSync(committed, "utf8");
  const regenerated = readFileSync(temporary, "utf8");

  if (expected !== regenerated) {
    console.error(
      "Contract drift: lib/api/schema.d.ts does not match ../backend/openapi.json.\n" +
        "Run `npm run gen:client` and commit the regenerated client.",
    );
    process.exit(1);
  }

  console.log("Contract in sync: lib/api/schema.d.ts matches ../backend/openapi.json.");
} finally {
  rmSync(temporary, { force: true });
}
