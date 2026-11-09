import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import ts from "typescript";

/** Load actual TypeScript with optional dependency stubs for server-action contract tests. */
export function loader(stubs = {}) {
  const modules = new Map();
  function load(url) {
    if (modules.has(url.href)) return modules.get(url.href).exports;
    const module = { exports: {} };
    modules.set(url.href, module);
    const code = ts.transpileModule(readFileSync(url, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText;
    const run = vm.runInThisContext(`(function(require, module, exports) {\n${code}\n})`, { filename: fileURLToPath(url) });
    const json = (name) => { const data = JSON.parse(readFileSync(new URL(name, url), "utf8")); return { ...data, default: data }; };
    run((name) => Object.hasOwn(stubs, name) ? stubs[name] : name.endsWith(".json") ? json(name) : load(new URL(`${name}.ts`, url)),
        module, module.exports);
    return module.exports;
  }
  return load;
}
