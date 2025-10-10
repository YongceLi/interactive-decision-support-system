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
    <div className="flex flex-col h-full bg-stone-50">
      {/* Header */}
          <div className="border-b border-stone-300 px-6 py-4 bg-red-800 text-white flex-shrink-0">
            <h2 className="text-lg font-semibold">
              Chat with our AI Agent
            </h2>
            <p className="text-sm text-red-100">
              Tell me about your vehicle preferences and I&apos;ll help you find the perfect match
            </p>
          </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 min-h-0">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`
                max-w-xs lg:max-w-md px-4 py-2 rounded-lg
                ${message.role === 'user'
                  ? 'bg-red-800 text-white'
                  : 'bg-stone-200 text-stone-800'
                }
              `}
            >
              <div className="text-sm whitespace-pre-wrap">{message.content}</div>
              <div className={`text-xs mt-1 ${
                message.role === 'user' ? 'text-red-100' : 'text-stone-500'
              }`}>
                {message.timestamp.toLocaleTimeString()}
              </div>
            </div>
          </div>
        ))}
        
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 text-gray-900 px-4 py-2 rounded-lg">
              <div className="flex items-center space-x-2">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                </div>
                <span className="text-sm">Agent is thinking...</span>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-stone-300 px-6 py-4 bg-stone-100 flex-shrink-0">
        <form onSubmit={handleSubmit} className="flex space-x-4">
          <input
            type="text"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            placeholder="Type your message..."
            className="flex-1 px-4 py-2 border border-stone-300 rounded-lg focus:ring-2 focus:ring-red-800 focus:border-transparent bg-white hover:border-stone-400 transition-colors duration-200"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={!inputMessage.trim() || isLoading}
            className="px-6 py-2 bg-red-800 text-white rounded-lg hover:bg-red-900 disabled:bg-stone-400 disabled:cursor-not-allowed transition-all duration-200 hover:scale-105 transform"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
