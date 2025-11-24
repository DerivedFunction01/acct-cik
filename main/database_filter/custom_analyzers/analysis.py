# custom_analyzers/analysis.py
import sqlite3
import pandas as pd
import json
import multiprocessing as mp
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class Config:
    """Simplified Config for Pipeline Analysis"""

    # We now pass the DB path dynamically per run
    db_path: str = "verified_active_data.db"
    output_dir: Path = field(default_factory=lambda: Path("./analysis_output"))
    num_workers: int = field(default_factory=mp.cpu_count)

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)


class DataLoader:
    def __init__(self, config: Config):
        self.config = config

    def load_checkpoint_data(self, limit=None):
        """
        Loads report data + matches from the current checkpoint DB.
        Used to select the sampling pool.
        """
        conn = sqlite3.connect(self.config.db_path)
        query = """
            SELECT r.cik, r.year, r.url 
            FROM report_data r
            JOIN webpage_result w ON r.url = w.url
            WHERE w.matches IS NOT NULL AND w.matches != '[]'
        """
        if limit:
            query += f" LIMIT {limit}"

        df = pd.read_sql_query(query, conn)
        conn.close()
        return df

    def load_document_lifecycle(self, url: str):
        """
        Fetches the state of a document in this DB:
        1. Sentences Kept (in webpage_result)
        2. Sentences Dropped (in discarded_sentences)
        """
        conn = sqlite3.connect(self.config.db_path)
        lifecycle = {}

        # 1. Get Survivors
        cursor = conn.cursor()
        cursor.execute("SELECT matches FROM webpage_result WHERE url=?", (url,))
        row = cursor.fetchone()
        if row and row[0]:
            try:
                matches = json.loads(row[0])
                for sent in matches:
                    lifecycle[sent] = {"status": "KEPT", "reason": "Active Signal"}
            except:
                pass

        # 2. Get Discards (Specific to this stage)
        try:
            cursor.execute(
                "SELECT sentence, discard_reason FROM discarded_sentences WHERE url=?",
                (url,),
            )
            for sent, reason in cursor.fetchall():
                lifecycle[sent] = {"status": "DISCARDED", "reason": reason}
        except sqlite3.OperationalError:
            # Table might not exist in early stages
            pass

        conn.close()
        return lifecycle


# (Remove PredictionsProcessor and BaseAnalyzer if not used, or keep as stubs)
class BaseAnalyzer:
    def __init__(self, config: Optional[Config], data_loader: Optional[DataLoader] = None):
        self.config = config or Config()
        self.data_loader = data_loader or DataLoader(self.config)

    def analyze(self, **kwargs):
        raise NotImplementedError
