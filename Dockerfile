FROM python:3.11-slim

RUN useradd -m sandboxuser

WORKDIR /sandbox

USER sandboxuser