"""Input-only limits: existing saved output remains readable."""
from typing import Annotated
from pydantic import StringConstraints

Title = Annotated[str, StringConstraints(strip_whitespace=True,min_length=1,max_length=100)]
Name = Annotated[str, StringConstraints(strip_whitespace=True,min_length=1,max_length=50)]
ShortText = Annotated[str, StringConstraints(max_length=200)]
Text4K = Annotated[str, StringConstraints(max_length=4000)]
Text8K = Annotated[str, StringConstraints(max_length=8000)]
Text12K = Annotated[str, StringConstraints(max_length=12000)]
Trait = Annotated[str, StringConstraints(strip_whitespace=True,min_length=1,max_length=100)]
