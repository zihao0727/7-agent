"use client";

import { useParams, useRouter } from "next/navigation";
import { ChatArea } from "@/components/ChatArea";

export default function ChatPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;

  return (
    <ChatArea
      sessionId={sessionId}
      onSessionIdChange={(id) => router.push(`/app/${id}`)}
    />
  );
}
