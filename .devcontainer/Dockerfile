FROM debian:bookworm-20240110-slim

# Install system packages
RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get -y upgrade \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    git \
    wget \
    g++ \
    ca-certificates \
    pipx \
    openssh-client \
    xz-utils \
    libcairo2 libcairo2-dev \
    tldr \
    && rm -rf /var/lib/apt/lists/*

### copy package requirements
COPY environment.yml conda-lock.yml /tmp/conda-tmp/
COPY pyproject.toml poetry.lock /tmp/poetry-tmp/
COPY id_rsa id_rsa.pub $HOME/.ssh/

### install miniconda
ARG conda_url=https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
RUN wget --output-document Miniconda3-Linux-x86_64.sh ${conda_url} \
    && mkdir $HOME/.conda \
    && bash Miniconda3-Linux-x86_64.sh -b -u -p $HOME/miniconda3 \
    && rm -f Miniconda3-Linux-x86_64.sh \
    && $HOME/miniconda3/bin/conda init bash  \
    && . $HOME/.bashrc

### read conda-lock.yml
ARG CONDA_ENV=kaggle_ssh
RUN pipx install conda-lock \
&& pipx ensurepath \
&& $HOME/.local/bin/conda-lock install -n ${CONDA_ENV} /tmp/conda-tmp/conda-lock.yml \
&& echo conda activate ${CONDA_ENV} >> $HOME/.bashrc

### install poetry dependencies within newly create conda env
ENV POETRY_NO_INTERACTION=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache
RUN $HOME/miniconda3/bin/conda run -n ${CONDA_ENV} poetry install --directory=/tmp/poetry-tmp/ \
&& rm -rf $POETRY_CACHE_DIR

### install playwright
RUN $HOME/miniconda3/bin/conda run --no-capture-output -n ${CONDA_ENV} playwright install-deps \
&& $HOME/miniconda3/bin/conda run --no-capture-output -n ${CONDA_ENV} playwright install

### generate pub key
#RUN ssh-keygen -t rsa -b 4096 -f $HOME/.ssh/id_rsa -N "" -C "automatically generated key with no password"
COPY id_rsa id_rsa.pub /root/.ssh/