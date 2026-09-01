const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

const PACKAGE_NAME = "@larksuite/cli";
const REGISTRY_URL = "https://registry.npmjs.org/@larksuite%2fcli/latest";
const UPDATE_INTERVAL_MS = 24 * 60 * 60 * 1000;

function safeSegment(value, fallback = "default") {
  const normalized = String(value ?? fallback).replace(/[^a-zA-Z0-9_.-]+/g, "_");
  return normalized.replace(/^[._-]+|[._-]+$/g, "") || fallback;
}

function compareVersions(left, right) {
  const a = String(left || "0").split(".").map((part) => Number.parseInt(part, 10) || 0);
  const b = String(right || "0").split(".").map((part) => Number.parseInt(part, 10) || 0);
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    if ((a[index] || 0) !== (b[index] || 0)) return (a[index] || 0) - (b[index] || 0);
  }
  return 0;
}

function readPackageVersion(packagePath) {
  try {
    return JSON.parse(fs.readFileSync(packagePath, "utf8")).version || null;
  } catch {
    return null;
  }
}

class LarkCliManager {
  constructor({ userDataDir, autoUpdate = true }) {
    this.userDataDir = userDataDir;
    this.autoUpdate = autoUpdate;
    this.runtimeDir = path.join(userDataDir, "lark-cli-runtime");
    this.configRoot = path.join(userDataDir, "lark-cli-config");
    this.lastUpdateCheckAt = 0;
    this.latestVersion = null;
    this.updatePromise = null;
    this.configuredProfiles = new Set();

    const bundledPackage = require.resolve(`${PACKAGE_NAME}/package.json`);
    this.bundledPackageDir = path.dirname(bundledPackage);
    this.bundledScript = path.join(this.bundledPackageDir, "scripts", "run.js");
    this.bundledVersion = readPackageVersion(bundledPackage);
    const npmPackage = require.resolve("npm/package.json");
    this.npmCli = path.join(path.dirname(npmPackage), "bin", "npm-cli.js");
  }

  managedPackagePath() {
    return path.join(this.runtimeDir, "node_modules", "@larksuite", "cli", "package.json");
  }

  managedScriptPath() {
    return path.join(this.runtimeDir, "node_modules", "@larksuite", "cli", "scripts", "run.js");
  }

  currentRuntime() {
    const managedVersion = readPackageVersion(this.managedPackagePath());
    if (managedVersion && fs.existsSync(this.managedScriptPath())) {
      return { source: "managed", version: managedVersion, script: this.managedScriptPath() };
    }
    return { source: "bundled", version: this.bundledVersion, script: this.bundledScript };
  }

  async status() {
    const runtime = this.currentRuntime();
    return {
      installed: Boolean(runtime.version && fs.existsSync(runtime.script)),
      source: runtime.source,
      version: runtime.version,
      latestVersion: this.latestVersion,
      updateAvailable: Boolean(
        this.latestVersion && runtime.version && compareVersions(this.latestVersion, runtime.version) > 0
      ),
    };
  }

  async ensureLatest({ force = false } = {}) {
    if (this.updatePromise) return this.updatePromise;
    this.updatePromise = this._ensureLatest({ force }).finally(() => {
      this.updatePromise = null;
    });
    return this.updatePromise;
  }

  async _ensureLatest({ force }) {
    const now = Date.now();
    if (!this.autoUpdate && !force) return this.status();
    if (!force && now - this.lastUpdateCheckAt < UPDATE_INTERVAL_MS) return this.status();
    this.lastUpdateCheckAt = now;

    try {
      const response = await fetch(REGISTRY_URL, { signal: AbortSignal.timeout(10_000) });
      if (!response.ok) throw new Error(`registry returned HTTP ${response.status}`);
      const metadata = await response.json();
      this.latestVersion = typeof metadata.version === "string" ? metadata.version : null;
    } catch (error) {
      return { ...(await this.status()), warning: `无法检查 lark-cli 更新：${error.message}` };
    }

    const current = this.currentRuntime();
    if (!this.latestVersion || compareVersions(this.latestVersion, current.version) <= 0) {
      return this.status();
    }

    fs.mkdirSync(this.runtimeDir, { recursive: true });
    const runtimePackage = path.join(this.runtimeDir, "package.json");
    if (!fs.existsSync(runtimePackage)) {
      fs.writeFileSync(
        runtimePackage,
        JSON.stringify({ name: "agent7-lark-cli-runtime", private: true }, null, 2),
        "utf8"
      );
    }
    try {
      await this._spawnNode(
        this.npmCli,
        [
          "install",
          "--prefix",
          this.runtimeDir,
          "--no-audit",
          "--no-fund",
          "--omit=dev",
          "--save-exact",
          `${PACKAGE_NAME}@${this.latestVersion}`,
        ],
        { timeoutSeconds: 180 }
      );
    } catch (error) {
      return { ...(await this.status()), warning: `lark-cli 自动升级失败：${error.message}` };
    }
    return this.status();
  }

  async runForUser({ userId, account, args, stdin = null, timeoutSeconds = 60 }) {
    if (!account || typeof account !== "object") throw new Error("缺少飞书账号配置");
    const profileName = safeSegment(account.profile_name, "default");
    const appId = String(account.app_id || "").trim();
    const appSecret = String(account.app_secret || "");
    const brand = account.brand === "lark" ? "lark" : "feishu";
    if (!appId || !appSecret) throw new Error("飞书 app_id 或 app_secret 为空");

    await this.ensureLatest();
    const runtime = this.currentRuntime();
    if (!runtime.version || !fs.existsSync(runtime.script)) throw new Error("lark-cli 不可用");

    const configDir = path.join(this.configRoot, `user_${safeSegment(userId, "unknown")}`);
    fs.mkdirSync(configDir, { recursive: true });
    const cleanArgs = this._normalizeArgs(args, profileName);
    const isConfigInit = cleanArgs[0] === "config" && cleanArgs[1] === "init";
    const profileKey = crypto
      .createHash("sha256")
      .update(`${userId}\0${profileName}\0${appId}\0${appSecret}`)
      .digest("hex");

    if (!isConfigInit && !this.configuredProfiles.has(profileKey)) {
      const configureArgs = [
        "--profile",
        profileName,
        "config",
        "init",
        "--name",
        profileName,
        "--app-id",
        appId,
        "--app-secret-stdin",
      ];
      if (brand === "lark") configureArgs.push("--brand", "lark");
      const configureResult = await this._executeCli(
        runtime.script,
        configureArgs,
        appSecret,
        configDir,
        timeoutSeconds
      );
      if (!configureResult.ok) {
        throw new Error(configureResult.stderr || "lark-cli profile initialization failed");
      }
      this.configuredProfiles.add(profileKey);
    }

    const result = await this._executeCli(
      runtime.script,
      ["--profile", profileName, ...cleanArgs],
      stdin,
      configDir,
      timeoutSeconds
    );
    if (isConfigInit && result.ok) this.configuredProfiles.add(profileKey);
    return result;
  }

  _normalizeArgs(args, expectedProfile) {
    if (!Array.isArray(args) || args.length === 0 || args.length > 200) {
      throw new Error("lark-cli 参数无效");
    }
    const normalized = args.map((value) => String(value));
    if (normalized.some((value) => value.length > 20_000 || value.includes("\0"))) {
      throw new Error("lark-cli 参数过长或包含非法字符");
    }
    if (normalized[0] === "--profile") {
      if (safeSegment(normalized[1], "") !== expectedProfile) {
        throw new Error("禁止跨用户配置执行 lark-cli");
      }
      normalized.splice(0, 2);
    }
    if (normalized.includes("--profile")) throw new Error("命令中不允许重复指定 profile");
    return normalized;
  }

  async _executeCli(script, args, stdin, configDir, timeoutSeconds) {
    const result = await this._spawnNode(script, args, {
      stdin,
      timeoutSeconds,
      env: {
        LARKSUITE_CLI_CONFIG_DIR: configDir,
        LARK_CLI_NO_PROXY: "1",
      },
    });
    return {
      ok: result.exitCode === 0,
      exit_code: result.exitCode,
      stdout: result.stdout,
      stderr: result.stderr,
    };
  }

  _spawnNode(script, args, { stdin = null, timeoutSeconds = 60, env = {} } = {}) {
    return new Promise((resolve, reject) => {
      const child = spawn(process.execPath, [script, ...args], {
        windowsHide: true,
        env: { ...process.env, ...env, ELECTRON_RUN_AS_NODE: "1" },
        stdio: ["pipe", "pipe", "pipe"],
      });
      let stdout = "";
      let stderr = "";
      let settled = false;
      const timer = setTimeout(() => {
        if (settled) return;
        child.kill();
        settled = true;
        reject(new Error("命令执行超时"));
      }, Math.max(1, timeoutSeconds) * 1000);
      child.stdout.on("data", (chunk) => {
        stdout += chunk.toString("utf8");
      });
      child.stderr.on("data", (chunk) => {
        stderr += chunk.toString("utf8");
      });
      child.on("error", (error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(error);
      });
      child.on("close", (code) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        const result = { exitCode: code ?? 1, stdout, stderr };
        if (result.exitCode !== 0 && script === this.npmCli) {
          reject(new Error(stderr.trim() || stdout.trim() || `npm exited with ${result.exitCode}`));
          return;
        }
        resolve(result);
      });
      if (stdin !== null && stdin !== undefined) child.stdin.end(String(stdin));
      else child.stdin.end();
    });
  }
}

module.exports = { LarkCliManager };
