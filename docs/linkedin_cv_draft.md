# LinkedIn / CV drafts — DO NOT PUBLISH without approval (D8)

Numbers verified from project artifacts.

## LinkedIn post draft

Built MarketMind, a Streamlit app that segments online retail customers with RFM + K-Means and estimates next-90-day spend with a leakage-safe time cutoff.

- Data: UCI Online Retail II (1,067,371 transactions → 797,885 cleaned rows; 5,942 customers with IDs)
- Segmentation: k=2 by silhouette (*Recent high-spend* vs *Lapsed low-spend*); hierarchical comparison included
- Model: gradient boosting selected on training CV MAE; held-out test MAE 452.10 vs mean baseline 609.26 (cutoff 2011-09-10)
- Lesson: high zero-purchase rates in the 90-day window make honest MAE/R² framing essential — R² 0.347 is not “accuracy”

Tools: Python, pandas, scikit-learn, Streamlit, joblib.

Demo: _URL pending approval_ · Repo: _pending_

## CV bullet draft

Built a customer segmentation and 90-day spend estimation pipeline on 1.07M UCI Online Retail II transactions (5,942 customers), delivering a Streamlit dashboard and a gradient-boosting model that improved held-out MAE to 452.10 from a 609.26 mean baseline (Python, scikit-learn, Streamlit).
