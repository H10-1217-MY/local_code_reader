import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
MAX_FILE_BYTES = int(os.getenv("MAX_FILE_BYTES", str(2 * 1024 * 1024)))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "300"))
MAX_QUESTION_CHARS = int(os.getenv("MAX_QUESTION_CHARS", "3000"))
MAX_CHAT_HISTORY_MESSAGES = int(os.getenv("MAX_CHAT_HISTORY_MESSAGES", "8"))

ALLOWED_EXTENSIONS = {
    ".py", ".pyw",
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh",
    ".js", ".jsx", ".ts", ".tsx",
    ".java", ".cs", ".go", ".rs",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".sh", ".bash", ".ps1", ".sql", ".md", ".txt",
}
