import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2, AlertCircle, Sparkles } from 'lucide-react';
import { sendMessageToBackend } from './api';

function App() {
  const [messages, setMessages] = useState([
    { 
      role: 'assistant', 
      text: 'Hello! I am Axiom, your AI assistant. How can I help you today?',
      provider: 'axiom'
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // Auto-scroll to the newest message
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = { role: 'user', text: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const data = await sendMessageToBackend(userMessage.text);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: data.response, provider: data.provider }
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: 'error', text: error.message }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-900 text-gray-100 font-sans">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 bg-gray-800 border-b border-gray-700 shadow-sm">
        <div className="flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-blue-400" />
          <h1 className="text-xl font-bold tracking-wide text-white">Axiom</h1>
        </div>
        <div className="text-xs font-medium px-2.5 py-1 bg-gray-700 text-gray-300 rounded-full">
          Multi-LLM Engine
        </div>
      </header>

      {/* Chat History */}
      <main className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
        {messages.map((msg, index) => (
          <div 
            key={index} 
            className={`flex gap-4 max-w-3xl mx-auto ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {/* Assistant/Error Avatar */}
            {msg.role !== 'user' && (
              <div className={`w-8 h-8 shrink-0 rounded-full flex items-center justify-center ${msg.role === 'error' ? 'bg-red-900/50 text-red-400' : 'bg-blue-600 text-white'}`}>
                {msg.role === 'error' ? <AlertCircle className="w-5 h-5" /> : <Bot className="w-5 h-5" />}
              </div>
            )}

            {/* Message Bubble */}
            <div 
              className={`relative px-5 py-3.5 rounded-2xl max-w-[85%] sm:max-w-[75%] shadow-sm leading-relaxed ${
                msg.role === 'user' 
                  ? 'bg-blue-600 text-white rounded-br-sm' 
                  : msg.role === 'error'
                  ? 'bg-red-900/20 border border-red-800/50 text-red-200 rounded-bl-sm'
                  : 'bg-gray-800 border border-gray-700 text-gray-200 rounded-bl-sm'
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.text}</p>
              
              {/* Provider Badge for Assistant */}
              {msg.role === 'assistant' && msg.provider !== 'axiom' && (
                <span className="absolute -bottom-5 left-1 text-[10px] uppercase font-bold tracking-wider text-gray-500">
                  via {msg.provider}
                </span>
              )}
            </div>

            {/* User Avatar */}
            {msg.role === 'user' && (
              <div className="w-8 h-8 shrink-0 rounded-full bg-gray-700 flex items-center justify-center text-gray-300">
                <User className="w-5 h-5" />
              </div>
            )}
          </div>
        ))}
        
        {/* Loading Indicator */}
        {isLoading && (
          <div className="flex gap-4 max-w-3xl mx-auto justify-start">
            <div className="w-8 h-8 shrink-0 rounded-full bg-blue-600 text-white flex items-center justify-center">
              <Bot className="w-5 h-5" />
            </div>
            <div className="px-5 py-4 rounded-2xl rounded-bl-sm bg-gray-800 border border-gray-700 flex items-center gap-2">
              <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
              <span className="text-sm text-gray-400 font-medium">Axiom is thinking...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </main>

      {/* Input Area */}
      <footer className="p-4 sm:p-6 bg-gray-900 border-t border-gray-800">
        <form 
          onSubmit={handleSubmit}
          className="max-w-3xl mx-auto relative flex items-center"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading}
            placeholder="Send a message to Axiom..."
            className="w-full bg-gray-800 border border-gray-700 text-white rounded-full pl-6 pr-14 py-4 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder-gray-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="absolute right-2 p-2 bg-blue-600 text-white rounded-full hover:bg-blue-500 disabled:opacity-50 disabled:hover:bg-blue-600 transition-colors"
          >
            <Send className="w-5 h-5" />
          </button>
        </form>
        <p className="text-center text-xs text-gray-500 mt-3">
          Axiom may display inaccurate info, so double-check its responses.
        </p>
      </footer>
    </div>
  );
}

export default App;
