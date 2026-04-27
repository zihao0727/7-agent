"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "./AuthProvider";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { loading, isAuthenticated } = useAuth();

  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated) {
      router.replace(`/login?next=${encodeURIComponent(pathname || "/app")}`);
    }
  }, [isAuthenticated, loading, pathname, router]);

  if (loading || !isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center bg-white dark:bg-[#0f0f0f]">
        <div className="flex items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
          <Loader2 className="h-5 w-5 animate-spin" />
          正在验证登录状态...
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
