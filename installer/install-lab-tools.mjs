#!/usr/bin/env node
/**
 * SSPA Research Lab — Instalador MCP Bridge
 *
 * Personalizado para: __USER_NAME__ / __PROJECT_NAME__
 * Generado: __GENERATED_AT__
 *
 * Ejecutar con:  node install-lab-tools.mjs
 * Requiere:      Node.js >= 18  (https://nodejs.org)
 *
 * Este instalador:
 *  1. Descarga el MCP Bridge desde el servidor del Lab
 *  2. Instala sus dependencias npm
 *  3. Pregunta la ruta de tu vault Obsidian
 *  4. Configura Claude Code (~/.claude/mcp.json) automáticamente
 */

import https    from 'node:https';
import http     from 'node:http';
import fs       from 'node:fs';
import path     from 'node:path';
import os       from 'node:os';
import readline from 'node:readline';
import { execSync } from 'node:child_process';

/* ─── Valores personalizados (generados por el Lab) ─────────────────────── */
const CFG = {
  labUrl:    '__LAB_URL__',
  token:     '__LAB_TOKEN__',
  projectId: '__LAB_PROJECT_ID__',
  userName:  '__USER_NAME__',
  projName:  '__PROJECT_NAME__',
};
/* ─────────────────────────────────────────────────────────────────────────── */

// ─── Helpers de salida ────────────────────────────────────────────────────────

function banner(msg) {
  const line = '─'.repeat(Math.max(50, msg.length + 4));
  console.log(`\n┌${line}┐`);
  console.log(`│  ${msg.padEnd(line.length - 2)}│`);
  console.log(`└${line}┘`);
}

function step(n, msg)  { console.log(`\n[${n}/5] ${msg}`); }
function ok(msg)       { console.log(`      ✔  ${msg}`); }
function warn(msg)     { console.log(`      ⚠  ${msg}`); }
function fail(msg)     { console.error(`\n      ✘  ${msg}`); }

function ask(rl, q) {
  return new Promise(resolve => rl.question(q, resolve));
}

// ─── HTTP fetch con soporte de redirecciones ──────────────────────────────────

function httpGet(url, headers = {}) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith('https') ? https : http;
    lib.get(url, { headers }, res => {
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location) {
        return httpGet(res.headers.location, headers).then(resolve).catch(reject);
      }
      const chunks = [];
      res.on('data', d => chunks.push(d));
      res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString('utf-8') }));
    }).on('error', reject);
  });
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  banner(`SSPA Research Lab — Instalador de herramientas`);
  console.log(`\n  Usuario:  ${CFG.userName}`);
  console.log(`  Proyecto: ${CFG.projName}`);

  // ── Verificar Node.js >= 18 ───────────────────────────────────────────────
  const nodeMajor = parseInt(process.versions.node.split('.')[0], 10);
  if (nodeMajor < 18) {
    fail(`Se requiere Node.js 18 o superior. Versión actual: ${process.versions.node}`);
    console.error('\n  Descargá la versión LTS desde https://nodejs.org\n');
    process.exit(1);
  }

  // ── Paso 1: Preparar directorio de instalación ────────────────────────────
  step(1, 'Preparando directorio de instalación...');
  const installDir = path.join(os.homedir(), '.lab-tools', 'mcp-bridge');
  fs.mkdirSync(installDir, { recursive: true });
  ok(installDir);

  // ── Paso 2: Descargar mcp-lab-bridge.mjs ─────────────────────────────────
  step(2, 'Descargando MCP Bridge desde el servidor...');
  let bridgeSource;
  try {
    const res = await httpGet(
      `${CFG.labUrl}/api/v1/plugin/mcp-bridge`,
      { 'Authorization': `Bearer ${CFG.token}` }
    );
    if (res.status !== 200) {
      fail(`Error al descargar el bridge (HTTP ${res.status}).`);
      console.error('  Verificá tu conexión a internet y que el token no haya expirado.');
      console.error('  Si el token expiró, descargá un nuevo instalador desde el Lab.\n');
      process.exit(1);
    }
    bridgeSource = res.body;
  } catch (e) {
    fail(`No se pudo conectar con el servidor: ${e.message}`);
    console.error('  Verificá tu conexión a internet.\n');
    process.exit(1);
  }

  const bridgePath = path.join(installDir, 'mcp-lab-bridge.mjs');
  fs.writeFileSync(bridgePath, bridgeSource, 'utf-8');
  ok('mcp-lab-bridge.mjs guardado');

  // ── Paso 3: Instalar dependencias npm ────────────────────────────────────
  step(3, 'Instalando dependencias npm...');
  const pkgJson = {
    name: 'lab-mcp-bridge',
    version: '1.0.0',
    type: 'module',
    dependencies: {
      '@modelcontextprotocol/sdk': '^1.0.0',
      'node-fetch': '^3.3.0',
    },
  };
  fs.writeFileSync(
    path.join(installDir, 'package.json'),
    JSON.stringify(pkgJson, null, 2),
    'utf-8'
  );
  try {
    execSync('npm install --silent', { cwd: installDir, stdio: 'pipe' });
    ok('Dependencias instaladas correctamente');
  } catch (e) {
    fail('Error al instalar dependencias con npm.');
    console.error('  Asegurate de tener npm instalado (viene incluido con Node.js).');
    console.error('  https://nodejs.org\n');
    process.exit(1);
  }

  // ── Paso 4: Ruta del vault de Obsidian ───────────────────────────────────
  step(4, 'Configurando tu vault de Obsidian...');
  console.log();
  console.log('  Ingresá la ruta completa a tu vault de Obsidian.');

  if (process.platform === 'win32') {
    console.log('  Ejemplo Windows:  C:\\Users\\TuNombre\\Documents\\MiVault');
  } else if (process.platform === 'darwin') {
    console.log('  Ejemplo Mac:      /Users/TuNombre/Documents/MiVault');
  } else {
    console.log('  Ejemplo Linux:    /home/TuNombre/Documents/MiVault');
  }
  console.log('  (Si aún no tenés vault, presioná Enter y editalo luego.)');
  console.log();

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const vaultRaw  = (await ask(rl, '  Ruta del vault › ')).trim();
  rl.close();

  // Limpiar comillas accidentales
  const vaultPath = vaultRaw.replace(/^["']|["']$/g, '').trim();

  if (!vaultPath) {
    warn('No ingresaste una ruta. Podés configurarla más tarde editando ~/.claude/mcp.json.');
  } else if (!fs.existsSync(vaultPath)) {
    warn('La ruta ingresada no existe en este momento. Verificala luego.');
  } else {
    ok(`Vault encontrado: ${vaultPath}`);
  }

  // ── Paso 5: Escribir ~/.claude/mcp.json ──────────────────────────────────
  step(5, 'Configurando Claude Code...');
  const mcpConfigPath = path.join(os.homedir(), '.claude', 'mcp.json');

  // Leer configuración existente (puede haber otros servidores MCP)
  let existing = {};
  if (fs.existsSync(mcpConfigPath)) {
    try {
      existing = JSON.parse(fs.readFileSync(mcpConfigPath, 'utf-8'));
      ok('Configuración existente detectada — se fusionará');
    } catch {
      warn('Archivo mcp.json existente con formato inválido — se sobreescribirá');
    }
  }
  if (!existing.mcpServers) existing.mcpServers = {};

  // Normalizar separadores de ruta para compatibilidad cross-platform
  const bridgePathNorm = bridgePath.replace(/\\/g, '/');

  existing.mcpServers['lab-obsidian'] = {
    command: 'node',
    args: [bridgePathNorm],
    env: {
      VAULT_PATH:     vaultPath || '',
      LAB_URL:        CFG.labUrl,
      LAB_TOKEN:      CFG.token,
      LAB_PROJECT_ID: CFG.projectId,
    },
  };

  fs.mkdirSync(path.dirname(mcpConfigPath), { recursive: true });
  fs.writeFileSync(mcpConfigPath, JSON.stringify(existing, null, 2), 'utf-8');
  ok(mcpConfigPath);

  // ── Resumen final ─────────────────────────────────────────────────────────
  banner('✔  Instalación completada correctamente!');
  console.log();
  console.log('  MCP Bridge instalado en:');
  console.log(`    ${bridgePath}`);
  console.log();
  console.log('  Configuración guardada en:');
  console.log(`    ${mcpConfigPath}`);
  console.log();
  console.log('  Próximos pasos:');
  console.log('    1. Abrí Claude Code desde cualquier proyecto.');
  console.log('    2. El servidor MCP "lab-obsidian" estará disponible automáticamente.');
  if (!vaultPath || !fs.existsSync(vaultPath)) {
    console.log('    3. Editá el campo VAULT_PATH en:');
    console.log(`       ${mcpConfigPath}`);
  }
  console.log();
  console.log('  Nota: el token expira cada 72 h. Si el bridge deja de funcionar,');
  console.log('  descargá un nuevo instalador desde Herramientas → MCP Bridge en el Lab.');
  console.log();
}

main().catch(e => {
  fail(`Error inesperado: ${e.message}`);
  if (process.env.DEBUG) console.error(e);
  process.exit(1);
});
