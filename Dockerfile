FROM python:2.7

# Source mount
ENV SRC_DIR /opt/rollingpin

# Set up requirements
RUN mkdir -p $SRC_DIR
WORKDIR $SRC_DIR
COPY *requirements.txt $SRC_DIR
RUN pip install -r *requirements.txt
COPY setup.py $SRC_DIR
RUN python setup.py install

# Copy over source
COPY . $SRC_DIR

# Default command to run lint, tests, test coverage
CMD scripts/ci/test.sh
