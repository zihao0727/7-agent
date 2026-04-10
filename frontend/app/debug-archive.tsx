"use client";

/**
 * 档案下载调试页面
 * 用于测试 Base64 解码和下载功能是否正常
 */

import { useState } from "react";

const DEBUG_BASE64 = "eyJkZXRhaWwiOiJhcmNoaXZlX21lc3NhZ2XkuI3lrZjlnKgifQ==";

const DEBUG_MESSAGE = `下载成功！
文件名: WYCZC2026Z961_archive_message.zip
文件大小: 37 字节
base64内容: ${DEBUG_BASE64}`;

export default function ArchiveDownloadDebugPage() {
  const [testResult, setTestResult] = useState<string>("");

  const testRegex = () => {
    console.log("=== 测试正则表达式 ===");
    
    // 测试文件名正则
    const filenameMatch = DEBUG_MESSAGE.match(/文件名:\s*(\S+\.zip)/);
    console.log("文件名匹配:", filenameMatch);
    
    // 测试大小正则
    const sizeMatch = DEBUG_MESSAGE.match(/文件大小:\s*(\d+)\s*字节/);
    console.log("文件大小匹配:", sizeMatch);
    
    // 测试 base64 正则（单行）
    let base64Match = DEBUG_MESSAGE.match(/base64内容:\s*([^\n]+)/);
    console.log("Base64 匹配（单行）:", base64Match);
    
    // 测试 base64 正则（多行）
    if (!base64Match) {
      base64Match = DEBUG_MESSAGE.match(/base64内容:\s*([\s\S]*?)(?:\n\n|$)/);
      console.log("Base64 匹配（多行）:", base64Match);
    }

    const result = `
文件名: ${filenameMatch?.[1] || "❌ 未匹配"}
文件大小: ${sizeMatch?.[1] || "❌ 未匹配"} 字节
Base64: ${base64Match ? `✅ 匹配成功 (长度: ${base64Match[1].trim().length})` : "❌ 未匹配"}
Base64 内容: ${base64Match?.[1]?.trim()?.substring(0, 50) || "❌"}...
    `;
    
    setTestResult(result);
  };

  const testBase64Decode = () => {
    console.log("=== 测试 Base64 解码 ===");
    
    try {
      const base64 = DEBUG_BASE64;
      console.log("Base64 原文:", base64);
      
      const binaryString = atob(base64);
      console.log("解码后的二进制字符串长度:", binaryString.length);
      
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      console.log("Uint8Array 长度:", bytes.length);
      console.log("前 10 个字节:", Array.from(bytes.slice(0, 10)));
      
      setTestResult(`
✅ Base64 解码成功！
解码后的字节数: ${bytes.length}
前 10 个字节: ${Array.from(bytes.slice(0, 10)).join(", ")}
      `);
    } catch (error) {
      console.error("解码失败:", error);
      setTestResult(`❌ 解码失败: ${error}`);
    }
  };

  const testDownload = () => {
    console.log("=== 测试下载功能 ===");
    
    try {
      const base64 = DEBUG_BASE64;
      const filename = "WYCZC2026Z961_archive_message.zip";
      
      console.log("开始下载:", filename);
      
      // 解码
      const binaryString = atob(base64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      
      // 创建 Blob
      const blob = new Blob([bytes], { type: "application/zip" });
      console.log("Blob 创建成功，大小:", blob.size);
      
      // 创建下载链接
      const url = URL.createObjectURL(blob);
      console.log("ObjectURL 创建成功:", url);
      
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      console.log("触发点击...");
      a.click();
      
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        console.log("清理完成");
      }, 100);
      
      setTestResult(`✅ 下载已触发，文件: ${filename}`);
    } catch (error) {
      console.error("下载失败:", error);
      setTestResult(`❌ 下载失败: ${error}`);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-8">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold mb-8 text-gray-900 dark:text-white">
          📥 档案下载调试工具
        </h1>

        <div className="space-y-6">
          {/* 测试消息 */}
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold mb-3 text-gray-900 dark:text-white">
              测试消息
            </h2>
            <pre className="bg-gray-100 dark:bg-gray-900 p-3 rounded text-sm overflow-auto whitespace-pre-wrap break-words">
              {DEBUG_MESSAGE}
            </pre>
          </div>

          {/* 测试按钮 */}
          <div className="grid grid-cols-1 gap-3">
            <button
              onClick={testRegex}
              className="px-4 py-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium transition-colors"
            >
              测试正则表达式
            </button>
            <button
              onClick={testBase64Decode}
              className="px-4 py-3 rounded-lg bg-green-600 hover:bg-green-700 text-white font-medium transition-colors"
            >
              测试 Base64 解码
            </button>
            <button
              onClick={testDownload}
              className="px-4 py-3 rounded-lg bg-purple-600 hover:bg-purple-700 text-white font-medium transition-colors"
            >
              测试下载功能
            </button>
          </div>

          {/* 测试结果 */}
          {testResult && (
            <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
              <h2 className="text-lg font-semibold mb-3 text-gray-900 dark:text-white">
                测试结果
              </h2>
              <pre className="bg-gray-100 dark:bg-gray-900 p-3 rounded text-sm overflow-auto whitespace-pre-wrap break-words">
                {testResult}
              </pre>
            </div>
          )}

          {/* 调试提示 */}
          <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-4 border border-yellow-200 dark:border-yellow-800">
            <h3 className="font-semibold text-yellow-900 dark:text-yellow-100 mb-2">
              💡 调试提示
            </h3>
            <ul className="text-sm text-yellow-800 dark:text-yellow-200 space-y-1">
              <li>• 打开浏览器开发者工具（F12）查看控制台输出</li>
              <li>• 点击"测试正则表达式"验证文本解析是否正确</li>
              <li>• 点击"测试 Base64 解码"验证解码函数是否正常</li>
              <li>• 点击"测试下载功能"模拟完整的下载流程</li>
              <li>• 检查浏览器的下载文件夹中是否有新文件</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
