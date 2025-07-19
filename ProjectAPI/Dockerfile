FROM python:3.10-slim

WORKDIR /code

COPY ./api/requirements.txt /code/requirements.txt

COPY . /code

RUN pip install --no-cache-dir --upgrade -r /code/api/requirements.txt

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]