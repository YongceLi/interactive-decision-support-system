'use client';

import { useState, useRef, useEffect } from 'react';
import { ChatMessage } from '@/types/chat';

interface ChatBoxProps {
  messages: ChatMessage[];
  onSendMessage: (message: string) => void;
  isLoading: boolean;
}

export default function ChatBox({ messages, onSendMessage, isLoading }: ChatBoxProps) {
  const [inputMessage, setInputMessage] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputMessage.trim() && !isLoading) {
      onSendMessage(inputMessage.trim());
      setInputMessage('');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex space-x-4">
      <input
        type="text"
        value={inputMessage}
        onChange={(e) => setInputMessage(e.target.value)}
        placeholder="What are you looking for?"
        className="flex-1 px-6 py-5 bg-white border border-[#8b959e]/40 rounded-xl focus:ring-2 focus:ring-[#ff1323]/20 focus:border-[#ff1323] transition-all duration-200 placeholder-[#8b959e] text-black text-xl shadow-sm"
        disabled={isLoading}
      />
      <button
        type="submit"
        disabled={!inputMessage.trim() || isLoading}
        className="px-8 py-5 bg-gradient-to-r from-[#750013] to-[#8b1320] text-white rounded-xl hover:from-[#8b1320] hover:to-[#750013] disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 shadow-sm hover:shadow-md text-xl font-semibold"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
        </svg>
      </button>
    </form>
  );
}
