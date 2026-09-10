# AWS Lambda's container runtime interface client: CMD below is a handler
# reference ("module.path.handler"), not a shell command — the base image's
# ENTRYPOINT (/lambda-entrypoint.sh) loads it and invokes it per request.
FROM public.ecr.aws/lambda/python:3.11

# Install Python dependencies first (leveraging Docker layer caching)
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy application source code
COPY . ${LAMBDA_TASK_ROOT}/

# Mangum-wrapped FastAPI app (app/main.py:handler), invoked by API Gateway via AWS_PROXY
CMD ["app.main.handler"]