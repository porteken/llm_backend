FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENV HOME=/home/nonroot

RUN mkdir -p ${HOME} && \
    chmod 777 ${HOME} && \
    chmod g+s ${HOME}

ENV PATH="${HOME}/.local/bin:${PATH}"

WORKDIR ${HOME}

CMD ["python", "--version"]
