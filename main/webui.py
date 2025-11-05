from flask import Flask, render_template_string, jsonify, request
import pandas as pd
from pathlib import Path
import random
import requests
import json

app = Flask(__name__)

# --- CONFIGURATION ---
MODEL_SERVER_URL = "http://127.0.0.1:5000"  # The URL of your server2.py
TRAINING_DATA_PATH = "training_data.parquet"

# --- HTML & JAVASCRIPT TEMPLATE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generative Model WebUI</title>
    <style>
        body { font-family: sans-serif; margin: 0; background-color: #f4f4f9; display: flex; justify-content: center; }
        .container { width: 100%; max-width: 900px; margin: 20px; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); display: flex; flex-direction: column; height: 95vh; }
        header { padding: 20px; border-bottom: 1px solid #eee; }
        h1 { margin: 0; font-size: 1.5em; }
        .chat-window { flex-grow: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 20px; }
        .message { padding: 15px; border-radius: 8px; line-height: 1.5; max-width: 85%; }
        .user-message { background-color: #e1f5fe; align-self: flex-end; }
        .model-response { background-color: #f1f8e9; align-self: flex-start; white-space: pre-wrap; font-family: monospace; }
        .input-area { border-top: 1px solid #eee; padding: 20px; display: flex; gap: 10px; }
        textarea { flex-grow: 1; padding: 10px; border: 1px solid #ccc; border-radius: 4px; resize: vertical; font-size: 1em; }
        button { padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; font-size: 1em; }
        #send-btn { background-color: #4CAF50; color: white; }
        #sample-btn { background-color: #03A9F4; color: white; }
        #send-btn:disabled { background-color: #aaa; }
        .thinking {
            display: inline-block;
            animation: thinking-anim 1.5s infinite;
        }
        @keyframes thinking-anim {
            0%, 100% { content: 'Thinking.'; }
            33% { content: 'Thinking..'; }
            66% { content: 'Thinking...'; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header><h1>Model Interaction UI</h1></header>
        <div class="chat-window" id="chat-window">
            <div class="message model-response">Hello! Enter a prompt below or use the sample button to get started.</div>
        </div>
        <div class="input-area">
            <textarea id="prompt-input" rows="4" placeholder="Enter your prompt here..."></textarea>
            <button id="send-btn">Send</button>
            <button id="sample-btn">Sample Prompt</button>
        </div>
    </div>

    <script>
        const promptInput = document.getElementById('prompt-input');
        const sendBtn = document.getElementById('send-btn');
        const sampleBtn = document.getElementById('sample-btn');
        const chatWindow = document.getElementById('chat-window');

        async function sendPrompt() {
            const prompt = promptInput.value.trim();
            if (!prompt) return;

            // Disable button and clear input
            sendBtn.disabled = true;
            sendBtn.textContent = 'Thinking...';
            promptInput.value = '';

            // Display user message
            const userMessageDiv = document.createElement('div');
            userMessageDiv.className = 'message user-message';
            userMessageDiv.textContent = prompt;
            chatWindow.appendChild(userMessageDiv);

            // Create model response container
            const modelResponseDiv = document.createElement('div');
            modelResponseDiv.className = 'message model-response';
            modelResponseDiv.textContent = 'Thinking...';
            chatWindow.appendChild(modelResponseDiv);
            chatWindow.scrollTop = chatWindow.scrollHeight;

            try {
                const response = await fetch('{{ model_server_url }}/generate-stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: prompt })
                });

                if (!response.ok) {
                    throw new Error(`Server error: ${response.statusText}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';
                modelResponseDiv.textContent = ''; // Clear "Thinking..."

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    const chunk = decoder.decode(value, { stream: true });
                    fullResponse += chunk;
                    // Try to format as JSON as it streams for nice printing
                    try {
                        const parsed = JSON.parse(fullResponse + '"}'); // Hack to allow partial JSON parsing
                        modelResponseDiv.textContent = JSON.stringify(parsed, null, 2);
                    } catch (e) {
                        modelResponseDiv.textContent = fullResponse; // Fallback to raw text
                    }
                    chatWindow.scrollTop = chatWindow.scrollHeight;
                }
                // Final formatting
                try {
                    modelResponseDiv.textContent = JSON.stringify(JSON.parse(fullResponse), null, 2);
                } catch (e) {
                    // Already showing raw text, do nothing
                }

            } catch (error) {
                modelResponseDiv.textContent = `Error: ${error.message}`;
                console.error('Fetch error:', error);
            } finally {
                sendBtn.disabled = false;
                sendBtn.textContent = 'Send';
            }
        }

        sendBtn.addEventListener('click', sendPrompt);
        promptInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendPrompt();
            }
        });

        sampleBtn.addEventListener('click', async () => {
            try {
                const response = await fetch('/get-sample-prompt');
                const data = await response.json();
                if (data.prompt) {
                    promptInput.value = data.prompt;
                } else {
                    alert(data.error || 'Could not fetch sample prompt.');
                }
            } catch (error) {
                alert('Failed to connect to the WebUI server to get a sample.');
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE, model_server_url=MODEL_SERVER_URL)

@app.route('/get-sample-prompt')
def get_sample_prompt():
    """Fetches a random prompt from the training data parquet file."""
    training_data = Path(TRAINING_DATA_PATH)
    if not training_data.exists():
        return jsonify({"error": f"'{TRAINING_DATA_PATH}' not found."}), 404
    try:
        df = pd.read_parquet(training_data)
        if "prompt" in df.columns and not df.empty:
            sample_prompt = random.choice(df["prompt"].dropna().tolist())
            return jsonify({"prompt": sample_prompt})
        else:
            return jsonify({"error": "Parquet file is empty or missing 'prompt' column."}), 500
    except Exception as e:
        return jsonify({"error": f"Failed to read parquet file: {e}"}), 500

if __name__ == "__main__":
    print("="*50)
    print("🚀 Starting Generative Model WebUI")
    print(f"   Model server expected at: {MODEL_SERVER_URL}")
    print("   Please ensure server2.py is running.")
    print("   Open your browser and go to: http://127.0.0.1:5003")
    print("="*50)
    app.run(host="0.0.0.0", port=5003)