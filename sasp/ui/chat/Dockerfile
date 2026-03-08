FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir gradio>=4.0 requests
EXPOSE 7860
CMD ["python", "-m", "sasp.ui.chat.app"]
