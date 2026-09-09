import logging
from datetime import datetime
from pathlib import Path

from config import Settings, get_conf


class MonthlyFileHandler(logging.Handler):
	def __init__(self, directory: Path) -> None:
		super().__init__()
		self.directory = directory
		self.directory.mkdir(parents=True, exist_ok=True)
		self._month = ""
		self._stream = None

	def emit(self, record: logging.LogRecord) -> None:
		try:
			month = datetime.fromtimestamp(record.created).strftime("%Y-%m")
			if month != self._month:
				if self._stream:
					self._stream.close()
				self._month = month
				self._stream = (self.directory / f"metaetl-{month}.log").open("a", encoding="utf-8")
			self._stream.write(self.format(record) + "\n")
			self._stream.flush()
		except Exception:
			self.handleError(record)

	def close(self) -> None:
		if self._stream:
			self._stream.close()
			self._stream = None
		super().close()


def configure_logging(settings: Settings | None = None) -> logging.Logger:
	settings = settings or get_conf()
	logger = logging.getLogger("metaetl")
	if logger.handlers:
		return logger

	logger.setLevel(settings.log_level.upper())
	formatter = logging.Formatter(
		"%(asctime)s | %(levelname)s | %(name)s | %(message)s",
		datefmt="%Y-%m-%d %H:%M:%S",
	)
	log_directory = Path(settings.log_directory)
	log_directory.mkdir(parents=True, exist_ok=True)
	file_handler = MonthlyFileHandler(log_directory)
	file_handler.setFormatter(formatter)
	logger.addHandler(file_handler)

	console_handler = logging.StreamHandler()
	console_handler.setFormatter(formatter)
	logger.addHandler(console_handler)
	logger.propagate = False
	return logger


logger = configure_logging()
