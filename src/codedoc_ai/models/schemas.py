from pydantic import BaseModel
from typing import List, Optional

class FunctionSchema(BaseModel):
    id: str
    name: str
    source_code: str
    file_path: str
    args: List[str]
    docstring: Optional[str]
    return_type: Optional[str]
    start_line: int
    end_line: int