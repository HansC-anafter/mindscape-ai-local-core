#!/usr/bin/env node
/**
 * 简单的 Gateway 测试脚本
 *
 * 使用方法:
 *   node test-simple.js
 */

import { spawn } from 'child_process';
import { readFileSync } from 'fs';

const GATEWAY_SCRIPT = 'dist/index.js';

// 测试用例
const tests = [
  {
    name: 'tools/list',
    request: {
      jsonrpc: '2.0',
      id: 1,
      method: 'tools/list',
      params: {}
    }
  },
  {
    name: 'tools/call - Primitive (需要先知道工具名)',
    request: {
      jsonrpc: '2.0',
      id: 2,
      method: 'tools/call',
      params: {
        name: 'mindscape.tool.wordpress.list_posts',
        arguments: {
          workspace_id: process.env.MINDSCAPE_WORKSPACE_ID || 'default-workspace',
          inputs: {
            site_id: 'yogacookie.app',
            per_page: 5
          }
        }
      }
    }
  }
];

console.log('🧪 Gateway MVP 简单测试');
console.log('======================\n');

// 检查 Gateway 是否已编译
try {
  readFileSync(GATEWAY_SCRIPT);
} catch (err) {
  console.error('❌ Gateway 未编译，请先运行: npm run build');
  process.exit(1);
}

// 运行第一个测试（tools/list）
console.log('📋 测试 1: tools/list\n');
const test1 = tests[0];
const gateway = spawn('node', [GATEWAY_SCRIPT], {
  stdio: ['pipe', 'pipe', 'pipe']
});

let output = '';
let errorOutput = '';

gateway.stdout.on('data', (data) => {
  output += data.toString();
});

gateway.stderr.on('data', (data) => {
  errorOutput += data.toString();
  // stderr 用于 Gateway 日志，也输出
  process.stderr.write(data);
});

gateway.on('close', (code) => {
  console.log('\n📤 请求:');
  console.log(JSON.stringify(test1.request, null, 2));
  console.log('\n📥 响应:');

  try {
    const lines = output.split('\n').filter(line => line.trim());
    for (const line of lines) {
      try {
        const response = JSON.parse(line);
        console.log(JSON.stringify(response, null, 2));

        if (response.result && response.result.tools) {
          console.log(`\n✅ 成功！返回 ${response.result.tools.length} 个工具`);
          if (response.result.tools.length > 0) {
            console.log('\n前 3 个工具:');
            response.result.tools.slice(0, 3).forEach((tool, i) => {
              console.log(`  ${i + 1}. ${tool.name}`);
            });
          }
        }
      } catch (e) {
        // 不是 JSON，可能是其他输出
        if (line.trim()) {
          console.log(line);
        }
      }
    }
  } catch (e) {
    console.error('解析响应失败:', e);
    console.log('原始输出:', output);
  }

  console.log('\n✅ 测试完成');
  process.exit(code || 0);
});

// 发送请求
gateway.stdin.write(JSON.stringify(test1.request) + '\n');
gateway.stdin.end();

// 超时保护
setTimeout(() => {
  console.error('\n⏱️  测试超时（10秒）');
  gateway.kill();
  process.exit(1);
}, 10000);





