import React, { useState, useEffect, useRef } from 'react';
import Editor, { loader } from '@monaco-editor/react';
import { 
  BookOpen, 
  Cpu, 
  Send, 
  Play, 
  Sparkles, 
  Terminal, 
  Search, 
  Code, 
  RefreshCw, 
  AlertCircle, 
  CheckCircle,
  HelpCircle,
  Sun,
  Moon
} from 'lucide-react';
import './App.css';

const API_BASE = "http://localhost:8000";

export default function App() {
  // Settings & Theme State
  const [fontSize, setFontSize] = useState(16);
  const [theme, setTheme] = useState("dark"); // "dark" or "light"
  
  // Resizable Panel Widths
  const [leftWidth, setLeftWidth] = useState(300);
  const [rightWidth, setRightWidth] = useState(380);
  const [consoleHeight, setConsoleHeight] = useState(250);

  // Mouse event handlers for resizing left/right panels
  const handleLeftMouseDown = (e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = leftWidth;
    const handleMouseMove = (moveEvent) => {
      const deltaX = moveEvent.clientX - startX;
      setLeftWidth(Math.max(250, Math.min(500, startWidth + deltaX)));
    };
    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  const handleRightMouseDown = (e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = rightWidth;
    const handleMouseMove = (moveEvent) => {
      const deltaX = startX - moveEvent.clientX; // drag left to expand
      setRightWidth(Math.max(320, Math.min(650, startWidth + deltaX)));
    };
    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  const handleConsoleMouseDown = (e) => {
    e.preventDefault();
    const startY = e.clientY;
    const startHeight = consoleHeight;
    const handleMouseMove = (moveEvent) => {
      const deltaY = moveEvent.clientY - startY;
      setConsoleHeight(Math.max(120, Math.min(600, startHeight - deltaY)));
    };
    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  const [chatInputHeight, setChatInputHeight] = useState(120);

  const handleChatInputMouseDown = (e) => {
    e.preventDefault();
    const startY = e.clientY;
    const startHeight = chatInputHeight;
    const handleMouseMove = (moveEvent) => {
      const deltaY = moveEvent.clientY - startY;
      setChatInputHeight(Math.max(120, Math.min(400, startHeight - deltaY)));
    };
    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  // Problems State
  const [problems, setProblems] = useState([]);
  const [filteredProblems, setFilteredProblems] = useState([]);
  const [selectedProblem, setSelectedProblem] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Editor State
  const [code, setCode] = useState("");
  const [editorInstance, setEditorInstance] = useState(null);
  const [monacoInstance, setMonacoInstance] = useState(null);

  // Console State
  const [consoleLogs, setConsoleLogs] = useState([]);
  const [simResult, setSimResult] = useState(null);
  const [consoleTab, setConsoleTab] = useState("logs"); // "logs" or "metrics"

  // AI Chat State
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [isCompiling, setIsCompiling] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);

  const messagesEndRef = useRef(null);

  // Load problems on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/problems`)
      .then(res => res.json())
      .then(data => {
        setProblems(data);
        setFilteredProblems(data);
        if (data.length > 0) {
          selectProblem(data[0]);
        }
      })
      .catch(err => {
        console.error("Error loading problems:", err);
        setConsoleLogs([{
          type: "error",
          text: "🚨 无法连接到后端 API 服务。请确保后端 FastAPI 服务已在本地 8000 端口启动！"
        }]);
      });
  }, []);

  // Filter problems based on search query
  useEffect(() => {
    const query = searchQuery.toLowerCase();
    const filtered = problems.filter(p => 
      p.id.toLowerCase().includes(query) || 
      p.name.toLowerCase().includes(query) ||
      p.description.toLowerCase().includes(query)
    );
    setFilteredProblems(filtered);
  }, [searchQuery, problems]);

  // Debounced Syntax Checking (Monaco Linter)
  useEffect(() => {
    if (!code || !monacoInstance || !editorInstance) return;

    const timeoutId = setTimeout(() => {
      fetch(`${API_BASE}/api/lint`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      })
      .then(res => res.json())
      .then(markers => {
        const model = editorInstance.getModel();
        if (model) {
          monacoInstance.editor.setModelMarkers(model, "verilog-linter", markers);
        }
      })
      .catch(err => console.error("Linter connection error:", err));
    }, 1000); // 1000ms debounce

    return () => clearTimeout(timeoutId);
  }, [code, monacoInstance, editorInstance]);

  // Auto-scroll chat to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, isStreaming]);

  // Select problem & load initial code template
  const selectProblem = (problem) => {
    setSelectedProblem(problem);
    
    // Create initial stub template based on ports or generic module name
    let stub = `module TopModule (\n  // 请在此处声明端口，例如：\n  // input clk,\n  // output zero\n);\n\n  // 请在此处编写你的 RTL 逻辑\n\nendmodule\n`;
    
    // Parse ports line-by-line from problem description
    const lines = problem.description.split('\n');
    const portList = [];
    const portRegex = /^\s*-\s+(input|output)\s+([a-zA-Z0-9_]+)(?:\s*\(\s*(\d+)\s*bits?\s*\))?/i;
    for (const line of lines) {
      const match = line.match(portRegex);
      if (match) {
        const type = match[1].toLowerCase();
        const name = match[2];
        const bits = match[3];
        if (bits) {
          const width = parseInt(bits);
          if (width > 1) {
            portList.push(`  ${type} [${width-1}:0] ${name}`);
          } else {
            portList.push(`  ${type} ${name}`);
          }
        } else {
          portList.push(`  ${type} ${name}`);
        }
      }
    }
    
    if (portList.length > 0) {
      const ports = portList.join(',\n');
      stub = `module TopModule (\n${ports}\n);\n\n  // 请在此处编写你的 RTL 逻辑\n\nendmodule\n`;
    }
    
    setCode(stub);
    setConsoleLogs([{
      type: "info",
      text: `已选择题目: ${problem.id} - ${problem.name}，模板代码已载入。`
    }]);
    setSimResult(null);
    setConsoleTab("logs");
    
    // Clear chat messages when changing problem
    setChatMessages([
      {
        role: "tutor",
        content: `你好！我是你的 AI 硬件电路导师。我已经为你加载了题目 **${problem.id} - ${problem.name}**。\n\n请先仔细阅读左侧的接口描述与题目要求，在中间编辑器中编写 Verilog 代码，完成后点击 **“运行测试”**。如果有任何疑问或遇到了报错，点击 **“AI 助教诊断”** 或在下方直接向我提问！`
      }
    ]);
  };

  // Editor OnMount hook
  const handleEditorDidMount = (editor, monaco) => {
    setEditorInstance(editor);
    setMonacoInstance(monaco);
  };

  // Compile & Simulate Trigger
  const runTest = () => {
    if (!selectedProblem) return;
    setIsCompiling(true);
    setConsoleTab("logs");
    setConsoleLogs(prev => [...prev, { type: "info", text: "⚙️ 正在挂载 Docker 容器沙箱进行编译与仿真..." }]);

    fetch(`${API_BASE}/api/compile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        problem_key: selectedProblem.key,
        code: code
      })
    })
    .then(res => res.json())
    .then(data => {
      setIsCompiling(false);
      setSimResult(data);

      const logs = [];
      if (data.compile_status === "error") {
        logs.push({
          type: "error",
          text: `❌ 编译失败：\n${data.compile_raw_output}`
        });
      } else {
        if (data.compile_status === "warning") {
          logs.push({
            type: "warning",
            text: `⚠️ 编译警告：\n${data.compile_raw_output}`
          });
        } else {
          logs.push({
            type: "success",
            text: "✅ 编译成功！"
          });
        }

        // Add simulation logs
        if (data.sim_status === "success") {
          logs.push({
            type: "success",
            text: `🎉 仿真完全通过！通过率: 100%\n${data.sim_raw_output}`
          });
          setConsoleTab("metrics");
        } else if (data.sim_status === "failed") {
          logs.push({
            type: "error",
            text: `❌ 仿真结果不匹配！通过率: ${(data.rank * 100).toFixed(1)}%\n${data.sim_raw_output}`
          });
          setConsoleTab("metrics");
        } else {
          logs.push({
            type: "error",
            text: `❌ 仿真异常错误：\n${data.sim_raw_output}`
          });
        }
      }
      setConsoleLogs(logs);
    })
    .catch(err => {
      setIsCompiling(false);
      console.error(err);
      setConsoleLogs(prev => [...prev, {
        type: "error",
        text: "🚨 编译仿真请求发送失败，请检查后端状态或网络连接。"
      }]);
    });
  };

  // Call AI Tutor for diagnosing the current state
  const askAITutorDiag = () => {
    if (!selectedProblem) return;
    
    let errorType = "compile";
    let errorMessage = "未知错误";

    if (simResult) {
      if (simResult.compile_status === "error") {
        errorType = "compile";
        errorMessage = simResult.compile_raw_output;
      } else {
        errorType = "simulation";
        errorMessage = simResult.sim_raw_output;
      }
    } else {
      // If student hasn't run compilation but wants to ask, check if we have editor markers
      const model = editorInstance?.getModel();
      const markers = monacoInstance?.editor.getModelMarkers({ owner: "verilog-linter" }) || [];
      if (markers.length > 0) {
        errorType = "compile";
        errorMessage = markers.map(m => `TopModule.sv:${m.startLineNumber}: error: ${m.message}`).join('\n');
      } else {
        // General query
        sendChatMessage("请帮我检查一下我目前的 Verilog 代码设计，看看是否存在硬件电路缺陷或设计问题？");
        return;
      }
    }

    sendTutorRequest(errorType, errorMessage);
  };

  // Send structured tutor request
  const sendTutorRequest = (errorType, errorMessage) => {
    setIsStreaming(true);
    setChatMessages(prev => [
      ...prev,
      {
        role: "student",
        content: `助教，我遇到了${errorType === "compile" ? "编译" : "仿真"}报错。报错日志如下：\n\`\`\`\n${errorMessage}\n\`\`\`\n\n请帮我分析一下问题出在哪里，并给出修改思路。`
      },
      {
        role: "tutor",
        content: ""
      }
    ]);

    // Format chat history for backend (FastAPI expects role: str, content: str)
    const history = chatMessages.slice(1).map(msg => ({
      role: msg.role === "student" ? "user" : "assistant",
      content: msg.content
    }));

    const payload = {
      problem_key: selectedProblem.key,
      code: code,
      error_type: errorType,
      error_message: errorMessage,
      chat_history: history
    };

    fetch(`${API_BASE}/api/ai_tutor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    .then(response => {
      if (!response.body) throw new Error("ReadableStream not supported");
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let tutorMessage = "";

      function readChunk() {
        reader.read().then(({ done, value }) => {
          if (done) {
            setIsStreaming(false);
            return;
          }
          const chunkStr = decoder.decode(value);
          const lines = chunkStr.split('\n');
          
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const text = line.slice(6);
              tutorMessage += text;
              setChatMessages(prev => {
                const next = [...prev];
                next[next.length - 1] = {
                  role: "tutor",
                  content: tutorMessage
                };
                return next;
              });
            }
          }
          readChunk();
        });
      }
      readChunk();
    })
    .catch(err => {
      console.error(err);
      setIsStreaming(false);
      setChatMessages(prev => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "tutor",
          content: "🤖 抱歉，连接 AI 助教失败。请检查服务器网络。"
        };
        return next;
      });
    });
  };

  // Student manual text message submission
  const sendChatMessage = (textToSend = null) => {
    const msgText = textToSend || chatInput;
    if (!msgText.trim() || isStreaming) return;

    if (!textToSend) setChatInput("");
    setIsStreaming(true);

    setChatMessages(prev => [
      ...prev,
      { role: "student", content: msgText },
      { role: "tutor", content: "" }
    ]);

    const newMsg = { role: "student", content: msgText };
    const history = [...chatMessages.slice(1), newMsg].map(msg => ({
      role: msg.role === "student" ? "user" : "assistant",
      content: msg.content
    }));

    // Attach latest compile logs as contextual help if available
    let errorContext = "No compile run yet.";
    if (simResult) {
      errorContext = `Compile status: ${simResult.compile_status}. Sim status: ${simResult.sim_status}. Raw output: ${simResult.sim_raw_output}`;
    }

    const payload = {
      problem_key: selectedProblem?.key || "unknown",
      code: code,
      error_type: "general_chat",
      error_message: errorContext,
      chat_history: history
    };

    fetch(`${API_BASE}/api/ai_tutor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    .then(response => {
      if (!response.body) throw new Error("ReadableStream not supported");
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let tutorMessage = "";

      function readChunk() {
        reader.read().then(({ done, value }) => {
          if (done) {
            setIsStreaming(false);
            return;
          }
          const chunkStr = decoder.decode(value);
          const lines = chunkStr.split('\n');
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const text = line.slice(6);
              tutorMessage += text;
              setChatMessages(prev => {
                const next = [...prev];
                next[next.length - 1] = {
                  role: "tutor",
                  content: tutorMessage
                };
                return next;
              });
            }
          }
          readChunk();
        });
      }
      readChunk();
    })
    .catch(err => {
      console.error(err);
      setIsStreaming(false);
      setChatMessages(prev => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "tutor",
          content: "🤖 抱歉，AI 助教在流式输出中出错。"
        };
        return next;
      });
    });
  };

  // Simple Markdown Renderer
  const renderMarkdown = (text) => {
    if (!text) return "";
    
    // Escape HTML
    let html = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
      
    // Code blocks: ```verilog ... ```
    html = html.replace(/```(verilog|diff|text|json|bash)?\n([\s\S]*?)\n```/g, (match, lang, code) => {
      const isDiff = lang === 'diff';
      // Format diff styles
      let lines = code.split('\n');
      if (isDiff) {
        lines = lines.map(l => {
          if (l.startsWith('+')) return `<span style="color:#10b981;font-weight:500;">${l}</span>`;
          if (l.startsWith('-')) return `<span style="color:#ef4444;font-weight:500;">${l}</span>`;
          return l;
        });
      }
      return `<pre><code class="mono">${lines.join('\n')}</code></pre>`;
    });
    
    // Inline code
    html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    
    // Headings
    html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
    html = html.replace(/^## (.*$)/gim, "<h2>$1</h2>");
    
    // Bold
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    
    // Unordered Lists
    html = html.replace(/^\s*-\s+(.*$)/gim, "<ul><li>$1</li></ul>");
    html = html.replace(/<\/ul>\s*<ul>/g, ""); // Collapse adjacent lists
    
    // Line breaks
    html = html.replace(/\n/g, "<br />");
    
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  };

  return (
    <div className={`app-container theme-${theme}`} style={{ '--base-font-size': `${fontSize}px` }}>
      {/* Top Header */}
      <header className="app-header">
        <div className="logo-section">
          <Cpu className="logo-icon" size={24} />
          <h1>RTL-Tutor</h1>
          <span className="model-badge">DeepSeek-V3 硬件教学版</span>
        </div>
        <div className="header-controls">
          <div className="control-item">
            <span className="control-label">字号: {fontSize}px</span>
            <input 
              type="range" 
              min="13" 
              max="24" 
              value={fontSize} 
              onChange={(e) => setFontSize(parseInt(e.target.value))}
              className="font-slider"
            />
          </div>
          <button 
            className="theme-toggle-btn"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            title="切换明暗主题"
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <div className="header-divider"></div>
          <div className="status-info">
            <div>编译器: <span style={{color:'var(--accent-cyan)'}}>iverilog (v12)</span></div>
            <div>沙箱状态: <span style={{color:'var(--success)'}}>Docker 容器隔离</span></div>
          </div>
        </div>
      </header>

      {/* Main Workspace */}
      <div className="workspace">
        
        {/* Left Column: Problem List & Spec */}
        <div className="left-panel" style={{ width: `${leftWidth}px` }}>
          <div className="search-container">
            <div style={{ position: 'relative' }}>
              <input 
                type="text" 
                placeholder="搜索题目 (ID、名称)..." 
                className="search-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <Search size={14} style={{ position: 'absolute', right: '12px', top: '11px', color: 'var(--text-muted)' }} />
            </div>
          </div>

          <div className="problems-list">
            {filteredProblems.map((p) => (
              <div 
                key={p.key} 
                className={`problem-card ${selectedProblem?.key === p.key ? 'active' : ''}`}
                onClick={() => selectProblem(p)}
              >
                <span className="problem-name">{p.id} {p.name}</span>
                <span className="problem-id">{p.id}</span>
              </div>
            ))}
          </div>

          {selectedProblem && (
            <div className="problem-desc-container">
              <h3>📄 接口与设计说明</h3>
              <div className="problem-desc">{selectedProblem.description}</div>
            </div>
          )}
        </div>

        <div className="resizer-handle" onMouseDown={handleLeftMouseDown}></div>

        {/* Center Column: Monaco Editor & Output Console */}
        <div className="center-panel">
          {/* Editor Header Bar */}
          <div className="editor-header">
            <div className="editor-title">
              <Code size={16} />
              <span>TopModule.sv (在线设计区)</span>
            </div>
            <div className="editor-actions">
              <button 
                className="glow-btn" 
                onClick={runTest}
                disabled={isCompiling || !selectedProblem}
                style={{ background: 'var(--accent-gradient)' }}
              >
                {isCompiling ? <RefreshCw className="animate-spin" size={16} /> : <Play size={16} />}
                <span>运行测试</span>
              </button>
              <button 
                className="glow-btn"
                onClick={askAITutorDiag}
                disabled={isStreaming || !selectedProblem}
                style={{ background: 'rgba(6, 182, 212, 0.1)', border: '1px solid rgba(6, 182, 212, 0.3)', color: 'var(--accent-cyan)' }}
              >
                <Sparkles size={16} />
                <span>AI 助教诊断</span>
              </button>
            </div>
          </div>

          {/* Monaco Editor Component */}
          <div className="editor-container">
            <Editor
              height="100%"
              language="verilog"
              theme={theme === 'dark' ? 'vs-dark' : 'light'}
              value={code}
              onChange={(value) => setCode(value || "")}
              onMount={handleEditorDidMount}
              options={{
                fontSize: fontSize,
                fontFamily: "'Fira Code', monospace",
                minimap: { enabled: false },
                lineNumbers: "on",
                roundedSelection: true,
                scrollBeyondLastLine: false,
                readOnly: isCompiling,
                automaticLayout: true,
              }}
            />
          </div>

          {/* Bottom Console Panel */}
          <div className="console-resizer-handle" onMouseDown={handleConsoleMouseDown}></div>
          <div className="console-panel" style={{ height: `${consoleHeight}px` }}>
            <div className="console-header" style={{ justifyContent: 'space-between' }}>
              <div className="console-tabs" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Terminal size={14} />
                <span 
                  style={{ cursor: 'pointer', color: consoleTab === 'logs' ? 'var(--text-primary)' : 'var(--text-secondary)' }}
                  onClick={() => setConsoleTab("logs")}
                >
                  输出日志 (Console Logs)
                </span>
                <span style={{ color: 'var(--card-border)' }}>|</span>
                <span 
                  style={{ cursor: 'pointer', color: consoleTab === 'metrics' ? 'var(--text-primary)' : 'var(--text-secondary)' }}
                  onClick={() => { if(simResult) setConsoleTab("metrics") }}
                >
                  仿真指标 (Simulation Metrics)
                </span>
                <span style={{ color: 'var(--card-border)' }}>|</span>
                <span 
                  style={{ cursor: 'pointer', color: consoleTab === 'waves' ? 'var(--text-primary)' : 'var(--text-secondary)' }}
                  onClick={() => setConsoleTab("waves")}
                >
                  时序波形 (Waveforms)
                </span>
              </div>

              {selectedProblem && (
                <div className="console-quick-actions" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <button 
                    className="quick-btn" 
                    disabled={isStreaming}
                    onClick={() => sendChatMessage("帮我指出当前代码中的硬件逻辑错误，但不要直接给我代码。")}
                  >
                    🔍 逻辑纠错
                  </button>
                  <button 
                    className="quick-btn"
                    disabled={isStreaming}
                    onClick={() => sendChatMessage("解释这道题目所要求的硬件电路原理（例如它是时序电路还是组合电路，有哪些特殊边缘触发）？")}
                  >
                    💡 原理说明
                  </button>
                  <button 
                    className="quick-btn"
                    disabled={isStreaming}
                    onClick={() => sendChatMessage("在 Verilog 语法中，这道题目涉及的赋值类型（阻塞与非阻塞）应该如何正确使用？")}
                  >
                    🔧 语法提示
                  </button>
                </div>
              )}
            </div>

            <div className="console-body">
              {consoleTab === "logs" ? (
                consoleLogs.length === 0 ? (
                  <div className="console-empty">
                    <Terminal size={24} />
                    <span>暂无编译和仿真结果，编写代码后点击“运行测试”。</span>
                  </div>
                ) : (
                  consoleLogs.map((log, i) => (
                    <div key={i} className={`log-item ${log.type}`}>
                      {log.text}
                    </div>
                  ))
                )
              ) : consoleTab === "metrics" ? (
                simResult && (
                  <div className="sim-results animated-fade-in">
                    <div className="sim-metric-grid">
                      <div className="sim-metric">
                        <span className="metric-label">编译状态</span>
                        <span className={`metric-value ${simResult.compile_status === 'success' ? 'success' : 'failed'}`}>
                          {simResult.compile_status.toUpperCase()}
                        </span>
                      </div>
                      <div className="sim-metric">
                        <span className="metric-label">仿真通过率 (Rank)</span>
                        <span className={`metric-value ${simResult.sim_status === 'success' ? 'success' : 'failed'}`}>
                          {(simResult.rank * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="sim-metric">
                        <span className="metric-label">时序对齐 / 不匹配</span>
                        <span className="metric-value" style={{ fontSize: '15px' }}>
                          共 {simResult.total_samples} 周期 / 错 {simResult.mismatches} 周期
                        </span>
                      </div>
                    </div>
                    <div className="progress-bar-container">
                      <div className="progress-bar" style={{ width: `${simResult.rank * 100}%` }}></div>
                    </div>
                  </div>
                )
              ) : (
                <WaveformViewer waveform={simResult?.waveform} />
              )}
            </div>
          </div>
        </div>

        <div className="resizer-handle" onMouseDown={handleRightMouseDown}></div>

        {/* Right Column: AI Tutor Dialogue */}
        <div className="right-panel" style={{ width: `${rightWidth}px` }}>
          <div className="chat-header">
            <Sparkles size={16} style={{ color: 'var(--accent-cyan)' }} />
            <span>AI 电路导师诊断台</span>
          </div>

          <div className="chat-messages">
            {chatMessages.map((msg, i) => (
              <div key={i} className={`chat-bubble ${msg.role}`}>
                {msg.role === 'tutor' && msg.content === "" ? (
                  <div className="streaming-loading">
                    <div className="dot"></div>
                    <div className="dot"></div>
                    <div className="dot"></div>
                  </div>
                ) : (
                  renderMarkdown(msg.content)
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Chat Input Area */}
          <div className="chat-input-resizer-handle" onMouseDown={handleChatInputMouseDown}></div>
          <div className="chat-input-area" style={{ height: `${chatInputHeight}px` }}>
            <div className="input-row">
              <textarea 
                className="chat-input" 
                placeholder="向 AI 电路导师提问或在此输入你的想法..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                disabled={isStreaming}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendChatMessage();
                  }
                }}
              />
              <button 
                className="send-btn" 
                onClick={() => sendChatMessage()}
                disabled={isStreaming || !chatInput.trim()}
              >
                <Send size={16} />
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

// SVG Waveform Viewer Component
function WaveformViewer({ waveform }) {
  if (!waveform || !waveform.signals || waveform.signals.length === 0) {
    return (
      <div className="waveform-empty">
        <Terminal size={24} style={{ opacity: 0.5 }} />
        <span>暂无时序波形数据。仿真成功运行且有波形输出时才会在此绘制。</span>
      </div>
    );
  }

  const { signals, timescale } = waveform;
  const rowHeight = 55;
  const scaleX = 8; // pixels per time unit
  const labelWidth = 140; // width of label column

  // Find max time from all changes
  const maxTime = Math.max(
    ...signals.flatMap(sig => sig.changes.map(c => c[0])),
    102 // default minimum time
  );

  const svgWidth = maxTime * scaleX + 40;
  const svgHeight = signals.length * rowHeight + 35; // extra space for time ticks

  // Generate grid ticks (e.g. every 10 units)
  const gridTicks = [];
  const tickInterval = maxTime > 200 ? 50 : (maxTime > 100 ? 10 : 5);
  for (let t = 0; t <= maxTime; t += tickInterval) {
    gridTicks.push(t);
  }

  // Helper to render single-bit wave path
  const getSingleBitPath = (changes) => {
    if (!changes || changes.length === 0) return "";
    
    // Sort changes by time
    const sorted = [...changes].sort((a, b) => a[0] - b[0]);
    let path = "";
    let lastY = rowHeight - 12; // lowY default
    
    for (let i = 0; i < sorted.length; i++) {
      const [t, val] = sorted[i];
      const x = t * scaleX;
      const y = val === "1" ? 12 : (val === "0" ? rowHeight - 12 : rowHeight / 2);
      
      if (i === 0) {
        path += `M 0 ${y}`;
      } else {
        // Vertical step transition
        path += ` H ${x} V ${y}`;
      }
      lastY = y;
    }
    
    // Extend to maxTime
    path += ` H ${maxTime * scaleX}`;
    return path;
  };

  // Helper to render multi-bit bus shapes and labels
  const renderMultiBitWave = (changes) => {
    if (!changes || changes.length === 0) return null;
    
    const sorted = [...changes].sort((a, b) => a[0] - b[0]);
    const segments = [];
    
    for (let i = 0; i < sorted.length; i++) {
      const [t1, val] = sorted[i];
      const t2 = (i + 1 < sorted.length) ? sorted[i+1][0] : maxTime;
      segments.push({ t1, t2, val });
    }
    
    const highY = 12;
    const lowY = rowHeight - 12;
    const midY = rowHeight / 2;
    const crossWidth = 4; // crossing boundary pixels

    return segments.map((seg, idx) => {
      const x1 = seg.t1 * scaleX;
      const x2 = seg.t2 * scaleX;
      const width = x2 - x1;
      
      if (width <= 0) return null;
      
      // Points for the hex polygon representing the bus segment
      let points = "";
      if (idx === 0) {
        // First segment - flat start
        points = `${x1},${highY} ${x2 - crossWidth},${highY} ${x2},${midY} ${x2 - crossWidth},${lowY} ${x1},${lowY}`;
      } else if (seg.t2 === maxTime) {
        // Last segment - flat end
        points = `${x1},${midY} ${x1 + crossWidth},${highY} ${x2},${highY} ${x2},${lowY} ${x1 + crossWidth},${lowY}`;
      } else {
        // Middle segment - hex both ends
        points = `${x1},${midY} ${x1 + crossWidth},${highY} ${x2 - crossWidth},${highY} ${x2},${midY} ${x2 - crossWidth},${lowY} ${x1 + crossWidth},${lowY}`;
      }
      
      const showText = width > 35;
      const formatValue = (v) => {
        if (/^[0-9A-Fa-f]+$/.test(v)) return `h'${v}`;
        return v;
      };

      return (
        <g key={idx}>
          <polygon 
            points={points} 
            fill="rgba(6, 182, 212, 0.15)" 
            stroke="var(--accent-cyan)" 
            strokeWidth="1.5" 
          />
          {showText && (
            <text 
              x={x1 + width / 2} 
              y={midY + 4} 
              textAnchor="middle" 
              fill="var(--text-primary)" 
              fontSize="10"
              fontFamily="monospace"
              style={{ pointerEvents: 'none' }}
            >
              {formatValue(seg.val)}
            </text>
          )}
        </g>
      );
    });
  };

  return (
    <div className="waveform-viewer">
      {/* Sticky Label Column */}
      <div className="waveform-labels" style={{ width: `${labelWidth}px` }}>
        <div className="waveform-label-header">信号名称 (Signals)</div>
        {signals.map((sig, idx) => (
          <div key={idx} className="waveform-label-row" style={{ height: `${rowHeight}px` }}>
            <span className="sig-name" title={sig.name}>{sig.name}</span>
            {sig.width > 1 && <span className="sig-width">[{sig.width - 1}:0]</span>}
          </div>
        ))}
      </div>

      {/* Scrolling SVG Waveform tracks */}
      <div className="waveform-canvas-container">
        <div className="waveform-canvas-header" style={{ width: `${svgWidth}px` }}>
          时间轴 (Timeline in {timescale})
        </div>
        
        <div className="waveform-scroll-area">
          <svg width={svgWidth} height={svgHeight} className="waveform-svg">
            {/* Grid & Time Ticks at Top */}
            <g className="waveform-timeline">
              {gridTicks.map((t) => {
                const x = t * scaleX;
                return (
                  <g key={t}>
                    <line 
                      x1={x} 
                      y1={20} 
                      x2={x} 
                      y2={svgHeight} 
                      stroke="var(--card-border)" 
                      strokeDasharray="2,3" 
                    />
                    <text 
                      x={x} 
                      y={15} 
                      textAnchor="middle" 
                      fill="var(--text-muted)" 
                      fontSize="10"
                      fontFamily="monospace"
                    >
                      {t}
                    </text>
                  </g>
                );
              })}
            </g>

            {/* Signal Waveforms */}
            <g transform="translate(0, 25)">
              {signals.map((sig, idx) => {
                const yOffset = idx * rowHeight;
                return (
                  <g key={idx} transform={`translate(0, ${yOffset})`}>
                    <line 
                      x1={0} 
                      y1={rowHeight} 
                      x2={maxTime * scaleX} 
                      y2={rowHeight} 
                      stroke="rgba(255, 255, 255, 0.05)" 
                    />
                    {sig.width === 1 ? (
                      <path 
                        d={getSingleBitPath(sig.changes)} 
                        fill="none" 
                        stroke={sig.name === "tb_mismatch" ? "var(--failed)" : "var(--accent-cyan)"} 
                        strokeWidth="2" 
                      />
                    ) : (
                      renderMultiBitWave(sig.changes)
                    )}
                  </g>
                );
              })}
            </g>
          </svg>
        </div>
      </div>
    </div>
  );
}
