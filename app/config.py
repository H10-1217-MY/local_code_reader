import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
MAX_FILE_BYTES = int(os.getenv("MAX_FILE_BYTES", str(2 * 1024 * 1024)))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "300"))
MAX_QUESTION_CHARS = int(os.getenv("MAX_QUESTION_CHARS", "3000"))
MAX_CHAT_HISTORY_MESSAGES = int(os.getenv("MAX_CHAT_HISTORY_MESSAGES", "8"))
MAX_PROJECT_FILES = int(os.getenv("MAX_PROJECT_FILES", "40"))

ALLOWED_EXTENSIONS = {
    ".py", ".pyw",
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh",
    ".js", ".jsx", ".ts", ".tsx",
    ".java", ".cs", ".go", ".rs",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".sh", ".bash", ".ps1", ".sql", ".md", ".txt",
    ".html", ".htm", ".css", ".scss", ".xml",
}

# 拡張子を持たない、または通常のsuffix判定だけでは拾いにくい代表的な開発ファイル。
ALLOWED_FILENAMES = {
    "Dockerfile", "Makefile", "CMakeLists.txt", "Procfile",
    ".gitignore", ".dockerignore", ".env.example",
    "Pipfile", "Pipfile.lock", "poetry.lock", "uv.lock",
    "yarn.lock", "pnpm-lock.yaml", "Cargo.lock", "go.mod", "go.sum",
}

# LLMに1ファイルずつ読ませなくても、プロジェクトの構成把握には役立つファイル。
# v2.3では内容から依存名・キーなどを機械的に抽出し、LLMの依存主張も静的情報で照合する。
PROJECT_STRUCTURE_ONLY_FILENAMES = {
    "requirements.txt", "requirements-dev.txt", "requirements-test.txt",
    "pyproject.toml", "Pipfile", "Pipfile.lock", "poetry.lock", "uv.lock",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
    ".gitignore", ".dockerignore", ".env.example", "tsconfig.json",
}

# 選択されても解析価値が低い、または生成物として扱う代表例。
PROJECT_EXCLUDED_FILENAMES = {
    ".DS_Store", ".gitkeep", "Thumbs.db", "desktop.ini",
}
