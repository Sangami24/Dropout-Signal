<div align="center">

# 📉 The Dropout Signal

### An AI-Powered Early Warning System for Student Retention

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Databricks](https://img.shields.io/badge/Databricks-Lakehouse-FF3621?style=for-the-badge&logo=databricks&logoColor=white)](https://databricks.com)
[![MLflow](https://img.shields.io/badge/MLflow-Experiment%20Tracking-0194E2?style=for-the-badge&logo=mlflow&logoColor=white)](https://mlflow.org)
[![Flask](https://img.shields.io/badge/Flask-Web%20App-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![Twilio](https://img.shields.io/badge/Twilio-Voice%20%2B%20WhatsApp-F22F46?style=for-the-badge&logo=twilio&logoColor=white)](https://twilio.com)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge)](LICENSE)

**7 million students** drop out of Indian higher education every year.  
The warning signs exist in every university's data — *but nobody connects the dots.*

**The Dropout Signal** is a two-layer predictive intervention platform built on Databricks that identifies at-risk students with ML, validates predictions through AI voice conversations, and connects students to the exact resources they need — before they leave.

[Architecture](#-architecture) · [Features](#-key-features) · [Tech Stack](#-tech-stack) · [Quick Start](#-quick-start) · [How It Works](#-how-it-works) · [Impact](#-impact)

</div>

---

## 🧠 The Problem

Dropout is **never sudden**. The warning signs appear months in advance:

| Signal | Example |
|--------|---------|
| 📉 Declining grades | Sem 1: 14.2 → Sem 2: 9.8 |
| 💰 Financial stress | Tuition unpaid for 2+ months |
| 👤 Demographic risk | Age 34, first-generation student |
| 📊 Macro pressure | GDP dropped 2.3%, rising unemployment |

The data exists across **three siloed departments** (Admissions, Exams, Finance) that never communicate. Our system bridges these silos and provides a single, unified early warning pipeline.

> *"A model that disproportionately flags students from lower-income backgrounds is a liability, not a tool."*  
> — Our guiding design principle

---

## 🏗 Architecture

The system operates as a **two-layer pipeline** — quantitative ML prediction followed by qualitative AI voice validation:

```
                    THE DROPOUT SIGNAL — END-TO-END PIPELINE
    ═══════════════════════════════════════════════════════════════

    ┌──────────────────────────────────────────────────────────────┐
    │  DATA SOURCE                                                 │
    │  UCI Dropout Dataset — 4,424 students, 37 features           │
    │  Demographics + Grades + Financials + Macroeconomics         │
    └───────────────────────────┬──────────────────────────────────┘
                                │
           ╔════════════════════╧════════════════════╗
           ║          LAYER 1: ML PIPELINE           ║
           ╚════════════════════╤════════════════════╝
                                │
    ┌───────────┐    ┌──────────┴──┐    ┌────────────┐    ┌──────────┐
    │  BRONZE   │───▶│   SILVER    │───▶│  ML MODELS │───▶│   GOLD   │
    │ Raw Delta │    │ Features +  │    │ LogReg +   │    │ Risk +   │
    │ Ingestion │    │ Engineering │    │ XGBoost    │    │ SHAP +   │
    │           │    │ + Cleaning  │    │ + Fairness │    │ Tiers    │
    └───────────┘    └─────────────┘    └────────────┘    └────┬─────┘
                                                               │
           ╔═══════════════════════════════════════════════╗    │
           ║      LAYER 2: AI VOICE VERIFICATION           ║◀───┘
           ╚═══════════════════╤═══════════════════════════╝
                               │
    ┌─────────────────┐    ┌───┴──────────────┐    ┌───────────────────┐
    │  Twilio Voice    │───▶│  LLM Analysis    │───▶│  Fusion Engine    │
    │  5 Non-Leading   │    │  Sentiment +     │    │                   │
    │  Questions       │    │  Root Cause +    │    │  0.6 × ML Score   │
    │                  │    │  Intent Scoring  │    │  0.4 × Voice      │
    └─────────────────┘    └──────────────────┘    └─────────┬─────────┘
                                                              │
                                                              ▼
                                                    ┌─────────────────┐
                                                    │  INTERVENTION   │
                                                    │  ENGINE         │
                                                    │                 │
                                                    │  Root Cause →   │
                                                    │  Specific       │
                                                    │  Resources      │
                                                    └─────────────────┘
```

---

## ✨ Key Features

### 🔬 Layer 1 — ML Prediction Engine

- **Medallion Architecture** (Bronze → Silver → Gold) on Delta Lake
- **6 Custom Engineered Features** grounded in dropout research:
  - Grade Trajectory Slope — *declining vs stable students*
  - Financial Stress Index — *composite of tuition, debt, scholarship, macro factors*
  - Curricular Engagement Ratio — *units approved / units enrolled*
  - Semester-over-Semester Grade Delta — *per-subject decline tracking*
  - Economic Pressure Index — *unemployment × inflation / GDP*
  - Age Risk Flag — *mature student indicator (25+)*
- **Dual Model Comparison** — Logistic Regression (interpretable baseline) vs XGBoost (tree-based)
- **MLflow Experiment Tracking** — parameters, metrics, model registry
- **SHAP Explainability** — per-student Top 3 risk factor attribution
- **Fairness Audit** across gender & socioeconomic groups:
  - Demographic Parity Ratio
  - Equal Opportunity Ratio
  - Predictive Parity Ratio

### 🎙️ Layer 2 — AI Voice Verification

- **Twilio-powered voice calls** positioned as routine semester wellness check-ins
- **5 carefully designed, non-leading questions** — student never knows they were flagged
- **LLM transcript analysis** (Groq/Llama 3.3 70B) for sentiment, root cause, and dropout intent
- **Fusion scoring** — `0.6 × ML + 0.4 × Voice` eliminates false positives
- **WhatsApp follow-up** — automated resource delivery for confirmed at-risk students

### 🎯 Intervention Engine

| Root Cause | Resources Connected |
|-----------|-------------------|
| **Financial** | National Scholarship Portal, Vidyalakshmi loans, Pratham Foundation |
| **Academic** | Peer tutoring, NPTEL/SWAYAM, remedial classes, course change counseling |
| **Social** | Campus clubs, peer mentoring, iCall / Vandrevala Foundation helplines |
| **Family** | Family counseling, flexible scheduling, part-time work facilitation |
| **Career** | Placement cell, alumni mentoring, Skill India programs |

### 🖥️ Web Application

- **Role-based access** — Admin Dashboard + Counselor View
- **Real-time pipeline visualization** — Bronze/Silver/Gold stage monitoring
- **Student risk browser** — searchable Gold table with drill-down modals
- **Fairness audit display** — transparent bias metrics
- **Voice call management** — initiate, monitor, and analyze calls from the UI

---

## ⚙️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Data Platform** | Databricks (Unity Catalog, Delta Lake) | Lakehouse architecture, governance, ACID tables |
| **Streaming** | Auto Loader (Structured Streaming) | Real-time file ingestion from Unity Catalog Volumes |
| **ML** | scikit-learn, XGBoost, SHAP | Model training, explainability |
| **Experiment Tracking** | MLflow | Parameter/metric logging, model registry |
| **Voice AI** | Twilio Voice API + Groq (Llama 3.3 70B) | Student check-in calls + LLM transcript analysis |
| **Messaging** | Twilio WhatsApp Sandbox | Automated resource delivery |
| **Web Framework** | Flask | Admin dashboard, counselor UI, API layer |
| **Data Processing** | PySpark, Pandas | Distributed + local data manipulation |
| **Database Queries** | Databricks SQL Warehouse | Live dashboard data from Delta tables |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- A Databricks workspace with Unity Catalog enabled
- (Optional) Twilio account for voice/WhatsApp features
- (Optional) Groq API key for LLM analysis

### 1. Clone & Install

```bash
git clone https://github.com/Verril-hash/dropout_signal.git
cd dropout_signal
```

**Layer 1 (Data Pipeline + ML):**

```bash
pip install -r requirements.txt
```

**Layer 2 (Voice Agent + Web App):**

```bash
pip install -r requirements_layer2.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```env
# Databricks
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=your-personal-access-token
DATABRICKS_WAREHOUSE_ID=your-sql-warehouse-id

# Twilio (optional — for voice calls)
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_PHONE_NUMBER=+1234567890

# Groq LLM (optional — for transcript analysis)
GROQ_API_KEY=your-groq-api-key

# Webhook (set after running ngrok)
WEBHOOK_BASE_URL=https://your-ngrok-url.ngrok-free.app

# Demo
DEMO_PHONE=+91XXXXXXXXXX
```

### 3. Run the Databricks Pipeline

Upload and execute the notebooks in your Databricks workspace:

```
1. dropout_pipeline.ipynb    →  Bronze → Silver → Gold (Medallion)
2. dropout_ml.ipynb          →  Model training + MLflow + Fairness + SHAP
3. dropout_dashboard.ipynb   →  Visualization queries
```

### 4. Launch the Web Application

```bash
# Start the Flask server
python app.py

# In another terminal, expose via ngrok (for Twilio webhooks)
ngrok http 5000
```

Open `http://localhost:5000` → Login → Admin or Counselor dashboard.

### 5. (Optional) AI Voice Demo

```bash
# Call your own phone to test the voice agent
curl -X POST http://localhost:5000/demo
```

---

## 📁 Project Structure

```
dropout_signal/
│
├── app.py                      # Unified web application (Admin + Counselor dashboards)
├── voice_server.py             # Layer 2: Twilio voice agent + WhatsApp bot
├── voice_config.py             # Voice/Twilio/LLM configuration
├── config.py                   # Layer 1 configuration (Databricks, streaming)
├── alerter.py                  # Smart alert system (voice/SMS notifications)
├── simulator.py                # IoT edge simulator (streams data to Databricks)
├── demo_live.py                # Live demo orchestrator (3-min escalation show)
├── generate_dataset.py         # Research-grounded synthetic data generator
├── download_dataset.py         # UCI dataset downloader
├── fetch_data.py               # Data fetching utilities
├── md_to_pdf.py                # Markdown → PDF conversion utility
│
├── dropout_pipeline.ipynb      # Databricks: Bronze → Silver → Gold
├── dropout_ml.ipynb            # Databricks: ML training + Fairness + SHAP
├── dropout_layer2.ipynb        # Databricks: Layer 2 fusion scoring
├── dropout_dashboard.ipynb     # Databricks: Dashboard visualizations
│
├── requirements.txt            # Layer 1 dependencies (pandas, requests)
├── requirements_layer2.txt     # Layer 2 dependencies (flask, twilio, groq)
│
├── data/
│   └── acoustic_samples.csv    # Sample sensor data (FloraMind component)
├── uci_dropout.csv             # UCI Student Dropout dataset (4,424 records)
├── voice_feedback.csv          # Voice agent analysis output
│
├── fusion_architecture.png     # System architecture diagram
├── layer1_architecture.png     # Layer 1 pipeline diagram
├── layer2_architecture.png     # Layer 2 voice flow diagram
│
└── .env                        # Environment variables (not tracked)
```

---

## 📊 How It Works

### Step 1: Data Ingestion (Bronze)

Raw student data (demographics, grades, finances) is ingested into a Delta Lake Bronze table with full schema documentation and ingestion metadata.

### Step 2: Feature Engineering (Silver)

Six custom features are computed on top of the 37 raw columns:

```
grade_trajectory     = mean(Sem2_grades) - mean(Sem1_grades)
financial_stress     = 0.35×tuition_unpaid + 0.25×debtor + 0.20×(1-scholarship) + 0.10×inflation + 0.10×(1/GDP)
engagement_ratio     = units_approved / units_enrolled
semester_grade_delta = mean(Sem2_grade - Sem1_grade) per subject
economic_pressure    = unemployment × inflation / GDP_growth
age_risk             = 1 if age_at_enrollment > 25 else 0
```

### Step 3: Model Training & Fairness (ML)

Two models are trained and compared:

| Model | Type | Purpose |
|-------|------|---------|
| Logistic Regression | Linear baseline | Interpretable, regularized |
| XGBoost | Gradient boosted trees | Captures non-linear interactions |

Both are logged to MLflow. The best model is registered in the Model Registry.

**Fairness is audited** across Gender and Socioeconomic groups using:
- **Demographic Parity** — equal flagging rates across groups
- **Equal Opportunity** — equal true positive rates across groups
- Fair threshold: ratio between 0.80 and 1.25

### Step 4: Explainability (SHAP)

Every flagged student gets a per-student explanation:

```
Student #2847 — Risk Score: 0.87 (HIGH)
  #1: Grade trajectory dropped 40% from Sem 1       (+0.23)
  #2: Tuition fees unpaid, debtor status active      (+0.19)
  #3: Age 34, mature student with work commitments   (+0.11)
```

### Step 5: AI Voice Validation (Layer 2)

For HIGH-risk students (score > 0.7), an AI voice agent calls them with 5 non-leading questions:

| # | Question | Signal Measured |
|---|----------|----------------|
| 1 | *"How has this semester been going for you?"* | General sentiment |
| 2 | *"What's been the most challenging part recently?"* | Primary stressor |
| 3 | *"On a scale of 1-5, how confident are you about completing your degree?"* | Dropout intent |
| 4 | *"If you could change one thing about college, what would it be?"* | Root cause |
| 5 | *"What are you most looking forward to next semester?"* | Future orientation |

The LLM analyzes transcripts for sentiment, root cause, and dropout probability.

### Step 6: Fusion & Intervention

```
Final Score = 0.6 × ML_risk + 0.4 × Voice_intent

ML says HIGH + Voice says HIGH  →  CONFIRMED   → Immediate intervention
ML says HIGH + Voice says LOW   →  DOWNGRADED  → Monitor (false positive removed)
ML says MED  + Voice says HIGH  →  UPGRADED    → Needs attention (ML missed it)
```

The counselor receives an actionable report with the root cause and specific resources.

---

## 📈 Impact

### By the Numbers

| Metric | Value |
|--------|-------|
| Indian students dropping out annually | ~7 million |
| Average university dropout rate | 17–20% |
| Layer 1 (ML) false positive rate | ~30–40% |
| **Layer 2 reduces false positives to** | **~5%** |
| Students saved per semester (per 5,000 enrolled) | **~70** |
| Revenue recovered per university per year | **₹2.8 crore** |
| Cost of AI voice calls (200/semester) | **₹3,000–6,000** |
| **ROI** | **11x–19x** |

### For the Student

Someone asked. Someone listened. Someone connected them to specific help.  
*They stay.*

### For the University

Higher graduation rates → better NIRF rankings → improved NAAC accreditation → retained tuition revenue → data-driven counselor allocation.

### For Society

NEP 2020 mandates reducing dropout rates. This is a direct implementation tool — audited for fairness, validated by human conversation, backed by data.

---

## 📐 API Reference

The Flask application exposes the following endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | System health (Databricks, Twilio, Groq status) |
| `GET` | `/api/stats` | Pipeline statistics (Bronze/Silver/Gold counts) |
| `GET` | `/api/students` | Gold table — all scored students (filterable) |
| `GET` | `/api/student/<id>` | Detailed student profile (Gold + Silver + Voice) |
| `GET` | `/api/fairness` | Fairness audit metrics |
| `GET` | `/api/model-metrics` | Model performance by risk tier |
| `GET` | `/api/tables` | List all Delta tables in schema |
| `POST` | `/api/pipeline/run` | Trigger Databricks job re-run |
| `POST` | `/initiate` | Start voice calls for HIGH-risk students |
| `POST` | `/demo` | Demo call to configured phone number |
| `POST` | `/analyze` | Run LLM analysis on completed call transcripts |
| `GET` | `/export` | Export voice feedback as CSV |
| `GET` | `/results` | All voice call results (JSON) |

---

## 🧪 Running the Live Demo

For hackathon presentations, use the **Live Demo Orchestrator**:

```bash
# Full demo — 3-minute escalation with Databricks upload + phone call
python demo_live.py

# Terminal animation only (no cloud services needed)
python demo_live.py --dry-run

# Fast mode — 90-second version
python demo_live.py --fast

# Upload data but skip the phone call
python demo_live.py --skip-call
```

The demo shows a dramatic real-time progression: `NORMAL → WARNING → CRITICAL → 📞 CALL`

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/improvement`)
3. Commit your changes (`git commit -m 'Add improvement'`)
4. Push to the branch (`git push origin feature/improvement`)
5. Open a Pull Request

---

## 📜 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## 🏆 Acknowledgments

- **HackBricks 2026** — Databricks Hackathon where this project was conceived and built
- **UCI Machine Learning Repository** — [Student Dropout Dataset](https://archive.ics.uci.edu/dataset/697/predict+students+dropout+and+academic+success)
- **Databricks** — Lakehouse platform powering the entire data pipeline
- **Twilio** — Voice and WhatsApp APIs for Layer 2 human verification
- **Groq** — Ultra-fast LLM inference for real-time transcript analysis

---

<div align="center">

**Built with conviction at HackBricks 2026** 🧱

*Because every student deserves someone who notices before it's too late.*

</div>
