"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  FileUp,
  Globe,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  UploadCloud,
} from "lucide-react";
import {
  deleteKnowledgeDocument,
  fetchKnowledgeDocuments,
  ingestKnowledgeUrl,
  searchKnowledge,
  uploadKnowledgeFiles,
} from "@/lib/api";
import type { KnowledgeDocumentInfo, KnowledgeSearchResult } from "@/lib/types";
import { cn } from "@/lib/utils";

function formatDate(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate()
  ).padStart(2, "0")}`;
}

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocumentInfo[]>([]);
  const [results, setResults] = useState<KnowledgeSearchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [query, setQuery] = useState("");
  const filesRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  const stats = useMemo(() => {
    const chunks = documents.reduce((sum, doc) => sum + (doc.chunk_count || 0), 0);
    return { docs: documents.length, chunks };
  }, [documents]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setDocuments(await fetchKnowledgeDocuments());
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载文档库失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleFiles = async (fileList: FileList | null) => {
    const files = Array.from(fileList || []);
    if (!files.length || busy) return;
    setBusy("upload");
    setError(null);
    try {
      const created = await uploadKnowledgeFiles(files);
      setDocuments((prev) => [...created, ...prev]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传入库失败");
    } finally {
      setBusy(null);
      if (filesRef.current) filesRef.current.value = "";
      if (folderRef.current) folderRef.current.value = "";
    }
  };

  const handleUrl = async () => {
    const nextUrl = url.trim();
    if (!nextUrl || busy) return;
    setBusy("url");
    setError(null);
    try {
      const doc = await ingestKnowledgeUrl(nextUrl);
      setDocuments((prev) => [doc, ...prev]);
      setUrl("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "网页入库失败");
    } finally {
      setBusy(null);
    }
  };

  const handleSearch = async () => {
    const text = query.trim();
    if (!text || busy) return;
    setBusy("search");
    setError(null);
    try {
      setResults(await searchKnowledge(text, 8));
    } catch (e) {
      setError(e instanceof Error ? e.message : "检索失败");
    } finally {
      setBusy(null);
    }
  };

  const handleDelete = async (doc: KnowledgeDocumentInfo) => {
    if (!confirm(`从文档库删除「${doc.title}」吗？`)) return;
    setBusy(doc.id);
    setError(null);
    try {
      await deleteKnowledgeDocument(doc.id);
      setDocuments((prev) => prev.filter((item) => item.id !== doc.id));
      setResults((prev) => prev.filter((item) => item.document_id !== doc.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-white text-gray-950 dark:bg-[#0f0f0f] dark:text-gray-100">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-6 py-4 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100 dark:bg-white/10">
            <BookOpen className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">个人知识库</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {stats.docs} 个文档，{stats.chunks} 个可检索片段
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-gray-100"
          title="刷新"
        >
          <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
        </button>
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-y-auto p-6 xl:grid-cols-[420px_1fr]">
        <section className="flex min-h-0 flex-col gap-4">
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-white/10 dark:bg-white/[0.03]">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <UploadCloud className="h-4 w-4" />
              上传文件或文件夹
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => filesRef.current?.click()}
                disabled={!!busy}
                className="flex h-10 items-center justify-center gap-2 rounded-lg bg-gray-900 px-3 text-sm font-medium text-white disabled:opacity-40 dark:bg-white dark:text-gray-900"
              >
                {busy === "upload" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
                文件
              </button>
              <button
                type="button"
                onClick={() => folderRef.current?.click()}
                disabled={!!busy}
                className="flex h-10 items-center justify-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-sm font-medium text-gray-700 disabled:opacity-40 dark:border-white/10 dark:bg-[#111] dark:text-gray-200"
              >
                文件夹
              </button>
            </div>
            <input
              ref={filesRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => void handleFiles(e.target.files)}
            />
            <input
              ref={folderRef}
              type="file"
              multiple
              className="hidden"
              // @ts-expect-error webkitdirectory is supported by Chromium browsers.
              webkitdirectory=""
              onChange={(e) => void handleFiles(e.target.files)}
            />
          </div>

          <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-white/10 dark:bg-white/[0.03]">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <Globe className="h-4 w-4" />
              保存网页
            </div>
            <div className="flex gap-2">
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com/article"
                className="h-10 min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-3 text-sm outline-none focus:border-gray-400 dark:border-white/10 dark:bg-[#111]"
              />
              <button
                type="button"
                onClick={() => void handleUrl()}
                disabled={!url.trim() || !!busy}
                className="h-10 rounded-lg bg-gray-900 px-4 text-sm font-medium text-white disabled:opacity-40 dark:bg-white dark:text-gray-900"
              >
                入库
              </button>
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-white/10 dark:bg-white/[0.03]">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <Search className="h-4 w-4" />
              检索预览
            </div>
            <div className="flex gap-2">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleSearch();
                }}
                placeholder="搜索文档库..."
                className="h-10 min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-3 text-sm outline-none focus:border-gray-400 dark:border-white/10 dark:bg-[#111]"
              />
              <button
                type="button"
                onClick={() => void handleSearch()}
                disabled={!query.trim() || !!busy}
                className="h-10 rounded-lg bg-gray-900 px-4 text-sm font-medium text-white disabled:opacity-40 dark:bg-white dark:text-gray-900"
              >
                搜索
              </button>
            </div>
          </div>

          {error ? <p className="rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-500/10 dark:text-red-300">{error}</p> : null}
        </section>

        <section className="grid min-h-0 grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="min-h-0 rounded-lg border border-gray-200 dark:border-white/10">
            <div className="border-b border-gray-200 px-4 py-3 text-sm font-medium dark:border-white/10">
              已入库文档
            </div>
            <div className="flex max-h-[680px] flex-col gap-2 overflow-y-auto p-3">
              {documents.length === 0 && !loading ? (
                <div className="flex h-40 items-center justify-center text-sm text-gray-400">
                  还没有入库文档。
                </div>
              ) : null}
              {documents.map((doc) => (
                <article key={doc.id} className="rounded-lg border border-gray-200 bg-white p-3 dark:border-white/10 dark:bg-[#111]">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h2 className="truncate text-sm font-semibold">{doc.title}</h2>
                      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {doc.source_type} · {doc.chunk_count} chunks · {formatDate(doc.updated_at)}
                      </p>
                      {doc.url ? (
                        <a href={doc.url} target="_blank" rel="noreferrer" className="mt-1 block truncate text-xs text-blue-600 dark:text-blue-300">
                          {doc.url}
                        </a>
                      ) : null}
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleDelete(doc)}
                      disabled={busy === doc.id}
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40 dark:hover:bg-red-500/10 dark:hover:text-red-300"
                      title="删除"
                    >
                      {busy === doc.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </div>

          <div className="min-h-0 rounded-lg border border-gray-200 dark:border-white/10">
            <div className="border-b border-gray-200 px-4 py-3 text-sm font-medium dark:border-white/10">
              检索结果
            </div>
            <div className="flex max-h-[680px] flex-col gap-2 overflow-y-auto p-3">
              {results.length === 0 ? (
                <div className="flex h-40 items-center justify-center text-sm text-gray-400">
                  输入关键词后可预览 Agent 会检索到的引用片段。
                </div>
              ) : null}
              {results.map((item, index) => (
                <article key={`${item.document_id}-${item.chunk_index}-${index}`} className="rounded-lg border border-gray-200 bg-white p-3 dark:border-white/10 dark:bg-[#111]">
                  <div className="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">
                    [{index + 1}] {item.source_label} · score {item.score}
                  </div>
                  <p className="text-sm leading-relaxed text-gray-800 dark:text-gray-200">
                    {item.text}
                  </p>
                </article>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
