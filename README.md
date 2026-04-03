# 🛡️ Sentinel-Claw
**An Adversarial, News-Aware Tri-Agent System for Intent-Enforced Trading.**

Sentinel-Claw is an autonomous trading framework built for the **ArmorIQ x OpenClaw Hackathon (2026)**. It solves the "hallucination risk" in AI finance by separating high-speed market reasoning from strict financial execution using an **Intent-Enforcement** architecture.

Instead of one AI making a guess, Sentinel-Claw uses an **Adversarial Committee** (Bull vs. Bear) and a **Deterministic Warden** (ArmorClaw) to ensure every trade follows a strict, human-defined policy.

---

## 🏗️ Architecture: The Tri-Agent Model
We utilize a multi-agent delegation chain to maximize security and satisfy the **Delegation Bonus** requirements:

1.  **The Bull Scout (Analyst):** Identifies technical momentum, growth signals, and "Buy" cases. (Zero API access).
2.  **The Bear Auditor (Risk):** Identifies fundamental risks, upcoming earnings blackouts, and volatility. (Zero API access).
3.  **The Warden (ArmorClaw):** The "Judge." It evaluates the debate between the scouts against the `policy.yaml`. It is the only component capable of authorizing an execution mandate.

---

## 💻 Hardware & Local Inference
This project is optimized for **Local Execution** on mobile workstations to ensure financial intent and private API keys never leave the local hardware.
* **CPU:** Intel Core i5-13450HX (13th Gen)
* **GPU:** NVIDIA RTX 4050 Laptop (6GB VRAM)
* **RAM:** 24GB DDR5
* **LLM Engine:** Ollama (Llama 3 8B - Quantized q4_0)

---

## 🚀 Setup & Installation

### 1. Prerequisites
* **Python 3.11** (Required for package stability)
* **Ollama:** [Download here](https://ollama.com)
* **Alpaca Markets:** [Sign up for Paper Trading Keys](https://alpaca.markets)

### 2. LLM Model Setup
Pull the lightweight model optimized for 6GB VRAM to prevent GPU memory overflow:
bash ollama pull llama3:8b-instruct-q4_0
# Clone the repository
git clone <your-repo-link>
cd sentinel-claw

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate

## Final

 **Gateway:** Start the OpenClaw security gateway: `openclaw gateway`.
**Execution:** Run `python main.py`.
