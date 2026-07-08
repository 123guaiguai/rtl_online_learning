import os
import re
import uuid
import shutil
import tempfile
import subprocess
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import openai

# Load Siliconflow credentials from api_keys
import sys
sys.path.append('/home/gq/Autochip_workspace/Experiments')
try:
    import api_keys
    SILICONFLOW_CONFIG = api_keys.SILICONFLOW_CONFIG
except ImportError:
    SILICONFLOW_CONFIG = {
        'api_key': os.getenv('SILICONFLOW_API_KEY', ''),
        'base_url': 'https://api.siliconflow.cn/v1'
    }

app = FastAPI(title="RTL-Tutor API Backend")

# Enable CORS for React Frontend (typically running on localhost:3000 or localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = "/home/gq/Autochip_workspace/Experiments"
VERILOG_EVAL_DIR = os.path.join(BASE_DIR, "VerilogEval")
DOCKER_IMAGE = "iverilog-sandbox"

# Pydantic request models
class CompileRequest(BaseModel):
    problem_key: str
    code: str

class LintRequest(BaseModel):
    code: str

class ChatMessage(BaseModel):
    role: str
    content: str

class TutorRequest(BaseModel):
    problem_key: str
    code: str
    error_type: str
    error_message: str
    chat_history: List[ChatMessage]


def clean_docker_output(text: str) -> str:
    """Filters out Docker-specific system warning messages from stdout/stderr."""
    cleaned_lines = []
    for line in text.splitlines():
        if "WARNING: Your kernel does not support" in line:
            continue
        if "Memory limited without swap" in line:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def parse_vcd(vcd_content: str) -> Dict[str, Any]:
    """Parses raw VCD (Value Change Dump) content into a structured timing format."""
    timescale = "1ps"
    signals = {}  # symbol -> {name, width, changes}
    
    lines = vcd_content.splitlines()
    i = 0
    
    # 1. Parse declarations
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
            
        if line.startswith("$timescale"):
            i += 1
            if i < len(lines):
                timescale = lines[i].strip().replace("$end", "").strip()
        elif line.startswith("$var"):
            parts = line.split()
            # Format: $var [type] [width] [symbol] [name] $end
            if len(parts) >= 5:
                width = parts[2]
                symbol = parts[3]
                name = parts[4]
                signals[symbol] = {
                    "name": name,
                    "width": int(width) if width.isdigit() else 1,
                    "changes": []
                }
        elif line.startswith("$enddefinitions"):
            i += 1
            break
        i += 1
        
    # 2. Parse transitions
    current_time = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
            
        if line.startswith("#"):
            time_str = line[1:]
            if time_str.isdigit():
                current_time = int(time_str)
        elif line.startswith("$dumpvars") or line.startswith("$end") or line.startswith("$dumpall"):
            pass
        else:
            if line.startswith('b') or line.startswith('r'):
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    val = parts[0][1:]
                    sym = parts[1]
                    if sym in signals:
                        signals[sym]["changes"].append([current_time, val])
            else:
                val = line[0]
                sym = line[1:]
                if sym in signals:
                    signals[sym]["changes"].append([current_time, val])
        i += 1
        
    signal_list = []
    for sym, sig in signals.items():
        signal_list.append({
            "name": sig["name"],
            "width": sig["width"],
            "changes": sig["changes"]
        })
        
    return {
        "timescale": timescale,
        "signals": signal_list
    }


def parse_compiler_errors(raw_output: str) -> List[Dict[str, Any]]:
    """
    Parse Icarus Verilog compiler stderr into Monaco Editor Marker format.
    Supports both "file.sv:line: error: msg" and "file.sv:line: msg" (e.g., syntax errors).
    """
    markers = []
    # Match patterns like: filename.sv:line: [error/warning:] message
    pattern = re.compile(r'^([^:\s]+\.[s]?v):(\d+):\s*(?:(error|warning|info):\s*)?(.*)$', re.IGNORECASE)
    
    for line in raw_output.splitlines():
        match = pattern.match(line)
        if match:
            filename, line_num_str, severity_str, msg = match.groups()
            
            # Only return markers for the student's module TopModule.sv
            if "TopModule" not in filename:
                continue
                
            line_num = int(line_num_str)
            
            # Map severity
            # 8 = MarkerSeverity.Error, 4 = MarkerSeverity.Warning, 1 = Hint/Info
            severity = 8
            if severity_str:
                sev_lower = severity_str.lower()
                if "warning" in sev_lower:
                    severity = 4
                elif "info" in sev_lower:
                    severity = 1
            else:
                # Default to error unless message explicitly says warning
                if "warning" in msg.lower():
                    severity = 4
            
            msg_text = msg.strip()
            if msg_text.lower() == "syntax error":
                msg_text = "语法错误 (syntax error)：请检查该行或前一行是否缺少分号 ';'，或者括号/分号/关键字是否配对。"
            
            markers.append({
                "severity": severity,
                "startLineNumber": line_num,
                "startColumn": 1,
                "endLineNumber": line_num,
                "endColumn": 100, # default highlight end column
                "message": msg_text
            })
    return markers


@app.get("/api/problems")
async def get_problems():
    """Reads problems.txt and loads available exercise details."""
    problems_file = os.path.join(VERILOG_EVAL_DIR, "problems.txt")
    if not os.path.exists(problems_file):
        raise HTTPException(status_code=500, detail="problems.txt not found in VerilogEval directory")
    
    problems = []
    with open(problems_file, 'r') as f:
        problem_keys = [line.strip() for line in f if line.strip()]
        
    for key in problem_keys:
        # Expected filename patterns: ProbXXX_name_prompt.txt
        prompt_path = os.path.join(VERILOG_EVAL_DIR, f"{key}_prompt.txt")
        description = ""
        if os.path.exists(prompt_path):
            with open(prompt_path, 'r') as pf:
                description = pf.read()
                
        # Parse display name
        parts = key.split('_', 1)
        prob_id = parts[0]
        prob_name = parts[1] if len(parts) > 1 else ""
        
        problems.append({
            "id": prob_id,
            "key": key,
            "name": prob_name,
            "description": description
        })
        
    return problems


@app.post("/api/compile")
async def compile_and_simulate(req: CompileRequest):
    """
    Runs student's code inside a lightweight Docker sandbox.
    Compiles it alongside the problem's reference model (if any) and testbench.
    """
    problem_key = req.problem_key
    student_code = req.code
    
    # 1. Validate paths
    testbench_path = os.path.join(VERILOG_EVAL_DIR, f"{problem_key}_test.sv")
    ref_path = os.path.join(VERILOG_EVAL_DIR, f"{problem_key}_ref.sv")
    
    if not os.path.exists(testbench_path):
        raise HTTPException(status_code=400, detail=f"Testbench for {problem_key} not found")
        
    # 2. Create sandbox temporary directory
    sandbox_id = str(uuid.uuid4())
    temp_dir = os.path.join("/tmp/rtl_tutor", f"sandbox_{sandbox_id}")
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        # Write student code
        student_file_path = os.path.join(temp_dir, "TopModule.sv")
        with open(student_file_path, "w") as f:
            f.write(student_code)
            
        # Copy testbench
        shutil.copy(testbench_path, os.path.join(temp_dir, "test.sv"))
        
        # Copy ref model if exists
        has_ref = os.path.exists(ref_path)
        if has_ref:
            shutil.copy(ref_path, os.path.join(temp_dir, "ref.sv"))
            
        # 3. Formulate the iverilog compilation command in Docker
        # We always prefix with 'sg docker -c' to ensure docker group rights take effect
        compile_cmd = (
            f"sg docker -c \"docker run --rm --network none --cpu-shares 512 --memory 128m "
            f"-v {temp_dir}:/workspace -w /workspace {DOCKER_IMAGE} "
            f"iverilog -Wall -Winfloop -Wno-timescale -g2012 -s tb -o tb.vvp "
            f"TopModule.sv test.sv"
        )
        if has_ref:
            compile_cmd += " ref.sv"
        compile_cmd += "\""
        
        # Run compilation
        comp_proc = subprocess.run(compile_cmd, shell=True, capture_output=True, text=True, timeout=5)
        
        # Clean compilation output of Docker warnings
        clean_stderr = clean_docker_output(comp_proc.stderr)
        clean_stdout = clean_docker_output(comp_proc.stdout)
        compile_raw = (clean_stdout + "\n" + clean_stderr).strip()
        
        # Compilation status parsing
        compile_status = "success"
        if comp_proc.returncode != 0:
            compile_status = "error"
        elif clean_stderr != "":
            compile_status = "warning"
            
        markers = parse_compiler_errors(clean_stderr)
        
        # If compilation failed, return early
        if compile_status == "error":
            return JSONResponse({
                "compile_status": compile_status,
                "compile_raw_output": compile_raw,
                "compile_errors": markers,
                "sim_status": "skipped",
                "sim_raw_output": "",
                "rank": -1.0,
                "total_samples": 0,
                "mismatches": 0,
                "waveform": None
            })
            
        # 4. If compile succeeded, execute simulation inside Docker sandbox
        sim_cmd = (
            f"sg docker -c \"docker run --rm --network none --cpu-shares 512 --memory 128m "
            f"-v {temp_dir}:/workspace -w /workspace {DOCKER_IMAGE} "
            f"vvp -n tb.vvp\""
        )
        
        sim_proc = subprocess.run(sim_cmd, shell=True, capture_output=True, text=True, timeout=5)
        
        # Parse simulation output and clean Docker warnings
        sim_raw = clean_docker_output(sim_proc.stdout + "\n" + sim_proc.stderr)
        sim_status = "success" if sim_proc.returncode == 0 else "failed"
        
        # Extract mismatches and samples
        mismatch_pattern = r"Mismatches: (\d+) in (\d+) samples"
        match = re.search(mismatch_pattern, sim_raw)
        
        mismatches = 0
        samples = 0
        rank = 1.0
        
        if match:
            mismatches = int(match.group(1))
            samples = int(match.group(2))
            if samples > 0:
                rank = (samples - mismatches) / samples
            if mismatches > 0:
                sim_status = "failed"
        else:
            # If mismatch line not found, check if simulation completed successfully
            if "success" not in sim_raw.lower() and "passed" not in sim_raw.lower():
                sim_status = "error"
                rank = 0.0
                
        # Read and parse VCD waveform if exists
        waveform_data = None
        vcd_path = os.path.join(temp_dir, "wave.vcd")
        if os.path.exists(vcd_path):
            try:
                with open(vcd_path, "r") as vf:
                    vcd_content = vf.read()
                waveform_data = parse_vcd(vcd_content)
            except Exception as ve:
                print(f"Error parsing VCD: {ve}")

        return {
            "compile_status": compile_status,
            "compile_raw_output": compile_raw,
            "compile_errors": markers,
            "sim_status": sim_status,
            "sim_raw_output": sim_raw,
            "rank": rank,
            "total_samples": samples,
            "mismatches": mismatches,
            "waveform": waveform_data
        }
        
    except subprocess.TimeoutExpired:
        return JSONResponse({
            "compile_status": "error",
            "compile_raw_output": "Execution timed out (Limit: 5 seconds). Possible infinite loop in simulation.",
            "compile_errors": [],
            "sim_status": "error",
            "sim_raw_output": "Execution timed out.",
            "rank": 0.0,
            "total_samples": 0,
            "mismatches": 0,
            "waveform": None
        }, status_code=200)
    finally:
        # Clean up sandbox temp dir
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/lint")
async def lint_code(req: LintRequest):
    """
    Debounced syntax checking endpoint. Runs iverilog -t null (parse only)
    inside the Docker sandbox and returns Monaco compatible error markers.
    """
    student_code = req.code
    
    sandbox_id = str(uuid.uuid4())
    temp_dir = os.path.join("/tmp/rtl_tutor", f"sandbox_lint_{sandbox_id}")
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        student_file_path = os.path.join(temp_dir, "TopModule.sv")
        with open(student_file_path, "w") as f:
            f.write(student_code)
            
        # Compile-check using iverilog's null target (-t null)
        lint_cmd = (
            f"sg docker -c \"docker run --rm --network none --cpu-shares 256 --memory 64m "
            f"-v {temp_dir}:/workspace -w /workspace {DOCKER_IMAGE} "
            f"iverilog -Wall -Winfloop -Wno-timescale -g2012 -t null TopModule.sv\""
        )
        
        proc = subprocess.run(lint_cmd, shell=True, capture_output=True, text=True, timeout=3)
        clean_stderr = clean_docker_output(proc.stderr)
        markers = parse_compiler_errors(clean_stderr)
        return markers
        
    except subprocess.TimeoutExpired:
        return []
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/ai_tutor")
async def ai_tutor_stream(req: TutorRequest):
    """
    Streams pedagogical feedback and suggestions using SiliconFlow's DeepSeek-V3 model.
    """
    # 1. Load problem prompt description
    prompt_path = os.path.join(VERILOG_EVAL_DIR, f"{req.problem_key}_prompt.txt")
    problem_description = ""
    if os.path.exists(prompt_path):
        with open(prompt_path, 'r') as f:
            problem_description = f.read()

    # 2. Formulate the system instructions
    system_prompt = (
        "你是一位非常有耐心且硬件开发经验丰富的数字电路（RTL）设计导师。\n"
        "目前有一名学生正在在线编写 Verilog 代码以完成一道题目。\n"
        "你的任务是指导学生，回答他的疑问，并引导他独立解决硬件调试问题。\n\n"
        f"学生当前面临的问题关键字：{req.problem_key}\n"
        f"题目详细描述与接口定义：\n{problem_description}\n\n"
        f"学生当前编写的 Verilog 代码：\n```verilog\n{req.code}\n```\n\n"
        f"当前电路的编译/仿真状态：\n{req.error_message}\n\n"
        "请遵循以下重要的教学与对话原则：\n"
        "1. 如果学生向你提出具体问题（例如询问语法、对比概念、解释硬件原理、问答），请**直接且专注地回答该具体问题**。不要套用“问题诊断”或“修改建议”等无关框架，也不要每次都强行分析他们代码的错误。\n"
        "2. 如果学生点击的是诊断按钮或要求诊断代码报错，你的回答应当结构清晰，可以使用 Markdown 标题（例如：### 问题诊断, ### 硬件原理科普, ### 修改建议）来进行排版，精准定位错误行数，以硬件思维来解释原理。\n"
        "3. **绝对不要直接给出整段完整正确的代码**。我们希望学生自主思考并调试。除非学生显式要求提供正确答案，或者同一个问题你与他已经交流了超过 4 轮，此时你才可以提供修复后的完整代码。\n"
        "4. 语气鼓励、亲切。"
    )

    # 3. Formulate the user instruction & Construct messages history
    messages = [{"role": "system", "content": system_prompt}]
    
    # Append past chat history (if any)
    for msg in req.chat_history:
        messages.append({"role": msg.role, "content": msg.content})
        
    # If not general chat, this is a diagnostic button click. Append a clear request.
    if req.error_type != "general_chat":
        user_content = (
            "请根据我当前编写的 Verilog 代码和遇到的编译/仿真错误，为我做一次详细的“问题诊断”，"
            "并提供相应的“硬件原理科普”与“修改建议”。"
        )
        messages.append({"role": "user", "content": user_content})

    # 5. Connect to SiliconFlow using compatible client
    client = openai.OpenAI(
        api_key=SILICONFLOW_CONFIG['api_key'],
        base_url=SILICONFLOW_CONFIG['base_url']
    )

    def stream_generator():
        try:
            response = client.chat.completions.create(
                model="deepseek-ai/DeepSeek-V3",
                messages=messages,
                temperature=0.2, # slightly lower temperature for engineering precision
                stream=True
            )
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    # SSE format: data: {content} \n\n
                    yield f"data: {text}\n\n"
        except Exception as e:
            yield f"data: 🤖 AI 助教连接失败，错误信息: {str(e)}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    # Launch uvicorn
    uvicorn.run("web_backend:app", host="0.0.0.0", port=8000, reload=True)
