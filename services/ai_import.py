import base64
import json
import os

from openai import OpenAI


client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def extract_json(text):
    start = text.find("{")
    end = text.rfind("}")
    return json.loads(text[start:end+1])


def analyze_scorecard(image_path):
    with open(image_path, "rb") as f:
        image = base64.b64encode(f.read()).decode()

    prompt = """
Les scorekort og returner JSON:

{
  "course_name": "",
  "hole_count": 18,
  "holes": [...],
  "tees": [...]
}
"""

    res = client.responses.create(
        model="gpt-4.1",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image",
                 "image_url": f"data:image/jpeg;base64,{image}"}
            ]
        }]
    )

    return extract_json(res.output_text)
