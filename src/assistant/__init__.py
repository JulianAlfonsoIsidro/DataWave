"""Part 6 Assistant package.

Conversational AI assistant for the Part 5 Streamlit webapp. Answers analyst
questions about the current promo run and past promos by calling tools that
wrap existing ``webapp_core`` functions, and pre-fills the promo form from an
uploaded campaign brief. Uses Amazon Bedrock when credentials are configured
and a fully offline Mock Mode otherwise.
"""
