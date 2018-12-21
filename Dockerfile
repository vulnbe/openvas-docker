FROM ubuntu:bionic as build

ARG version=10
ARG openvas_scanner="v6.0+beta2.tar.gz"
ARG gvm_libs="v1.0+beta2.tar.gz"
ARG gvmd="v8.0+beta2.tar.gz"
ARG gsa="v8.0+beta2.tar.gz"

ARG build_type="Release"
ARG install_dir="/openvas"
ARG install_prefix="/usr"
ARG bin_dir="/usr/bin"
ARG local_state_dir="/var"

ENV cmake_build_params="\
      -DCMAKE_BUILD_TYPE=${build_type} \
      -DCMAKE_INSTALL_PREFIX=${install_prefix} \
      -DSBINDIR=${bin_dir} \
      -DLOCALSTATEDIR=${local_state_dir} \
      -DSYSCONFDIR=/etc"

WORKDIR /root/

RUN apt update && \
    export DEBIAN_FRONTEND=noninteractive && \
    apt install -yq --no-install-recommends \
      curl \
      ca-certificates \
      gnupg \
      tzdata && \
    ln -fs /usr/share/zoneinfo/Europe/Moscow /etc/localtime && \
    dpkg-reconfigure --frontend noninteractive tzdata

# Installing build deps

RUN curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add - && \
    echo "deb https://dl.yarnpkg.com/debian/ stable main" | tee /etc/apt/sources.list.d/yarn.list && \
    apt update && \
    apt install -yq --no-install-recommends \
      bison \
      cmake \
      pkg-config \
      libglib2.0-dev \
      libgpgme-dev \
      libgnutls28-dev \
      uuid-dev \
      libssh-gcrypt-dev \
      libhiredis-dev \
      gcc \
      gettext \
      git \
      libpcap-dev \
      libksba-dev \
      libsnmp-dev \
      libgcrypt20-dev \
      libpq-dev \
      postgresql-server-dev-10 \
      libical-dev \
      libmicrohttpd-dev \
      libxml2-dev \
      libxslt1-dev \
      nodejs \
      python-polib \
      xsltproc \
      yarn && \
    mkdir -p ${install_dir}

# Building gvm libs

RUN curl -O -L "https://github.com/greenbone/gvm-libs/archive/${gvm_libs}" && \
    tar -xvf ${gvm_libs} && \
    cd gvm-libs* && \
    mkdir build && \
    cd build && \
    cmake ${cmake_build_params} .. && \
    make && \
    make DESTDIR=${install_dir} install && \
    make install

# Building openvas-scaner

RUN curl -O -L "https://github.com/greenbone/openvas-scanner/archive/${openvas_scanner}" && \
    tar -xvf ${openvas_scanner} && \
    cd openvas-scanner-* && \
    mkdir build && \
    cd build && \
    cmake ${cmake_build_params} .. && \
    make && \
    make DESTDIR=${install_dir} install

# Building gvmd

RUN curl -O -L "https://github.com/greenbone/gvmd/archive/${gvmd}" && \
    tar -xvf ${gvmd} && \
    cd gvmd-* && \
    mkdir build && \
    cd build && \
    cmake ${cmake_build_params} -DBACKEND=POSTGRESQL .. && \
    make && \
    make DESTDIR=${install_dir} install

# Building gsa

COPY ./gsa7.patch /tmp/

RUN curl -O -L "https://github.com/greenbone/gsa/archive/${gsa}" && \
    tar -xvf ${gsa} && \
    cd gsa-* && \
    if [ "${version}" = "9" ]; then \
      git apply /tmp/gsa7.patch || echo 'Git patch error'; \
    fi && \
    mkdir build && \
    cd build && \
    cmake ${cmake_build_params} .. && \
    make && \
    make DESTDIR=${install_dir} install && \
    mkdir -p ${install_dir}/${local_state_dir}/lib/openvas/gvmd/

FROM ubuntu:bionic

ARG version=10
ARG python_gvm="==1.0.0b2"
ARG install_dir="/openvas"

LABEL Author="Alexey Pronin a@vuln.be"

# Copy openvas binaries

COPY --from=build ${install_dir} /

# Installing additional packages

RUN apt update && \
    export DEBIAN_FRONTEND=noninteractive && \
    apt install -yq --no-install-recommends \
      ca-certificates \
      curl \
      doc-base \
      gettext \
      gnupg \
      gnutls-bin \
      haveged \
      iproute2 \
      iputils-* \
      libgpgme11 \
      libical3 \
      libhiredis0.13 \
      libmicrohttpd12 \
      libpcap0.8 \
      libsnmp30 \
      libssh-4 \
      libssh-gcrypt-4 \
      libxslt1.1 \
      nano \
      net-tools \
      nmap \
      python3 \
      python3-pip \
      python3-setuptools \
      python3-wheel \
      redis-server \
      rsync \
      snmp \
      socat \
      postgresql-10 \
      postgresql-contrib \
      supervisor \
      texlive-latex-base \
      preview-latex-style \
      texlive-latex-extra \
      texlive-latex-recommended \
      texlive-pictures \
      traceroute \
      tzdata \
      wget \
      xmlstarlet \
      xsltproc \
      zip && \
    ln -fs /usr/share/zoneinfo/Europe/Moscow /etc/localtime && \
    dpkg-reconfigure --frontend noninteractive tzdata && \
    pip3 install "python-gvm${python_gvm}" && \
    rm -rf /var/lib/apt/lists/*

# Adding symlinks GVM9 <-> GVM10

RUN if [ "${version}" = "9" ]; then \
      ln -s /usr/bin/openvasmd /usr/bin/gvmd; \
      ln -s /usr/bin/openvas-portnames-update /usr/bin/gvm-portnames-update; \
      ln -s /usr/bin/openvas-manage-certs /usr/bin/gvm-manage-certs; \
    fi

# Configuring PostgreSQL and preparing DB

RUN sed -i 's|^#checkpoint_timeout = 5min|checkpoint_timeout = 1h|;s|^#checkpoint_warning = 30s|checkpoint_warning = 0|' /etc/postgresql/10/main/postgresql.conf && \
    echo 'host all all 127.0.0.1/32 trust' >> /etc/postgresql/10/main/pg_hba.conf && \
    /etc/init.d/postgresql start && \
    pg_isready -h localhost -p 5432 && \
    while [ $? -ne 0 ]; do sleep 5; pg_isready -h localhost -p 5432; done && \
    su - postgres -c "createuser -DRS root" && \
    if [ "${version}" = "10" ]; then \
      su - postgres -c "createdb -O root gvmd"; \
      su - postgres -c "psql gvmd -c 'create role dba with superuser noinherit; grant dba to root; create extension \"uuid-ossp\";'"; \
    else \
      su - postgres -c "createdb -O root tasks"; \
      su - postgres -c "psql tasks -c 'create role dba with superuser noinherit; grant dba to root; create extension \"uuid-ossp\";'"; \
    fi && \
    /etc/init.d/postgresql stop

COPY ./redis.conf /etc/openvas-redis.conf
COPY ./entrypoint.py /
COPY ./gvm_client.py /

RUN chmod +x /entrypoint.py /gvm_client.py

# Creating cache of NVTs and other feeds

RUN gvm-manage-certs -a && \
    /entrypoint.py --create-cache

# Importing port names configuration

RUN /etc/init.d/postgresql start && \
    pg_isready -h localhost -p 5432 && \
    while [ $? -ne 0 ]; do sleep 5; pg_isready -h localhost -p 5432; done && \
    curl -O -L https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.xml && \
    gvm-portnames-update service-names-port-numbers.xml && \
    rm service-names-port-numbers.xml && \
    /etc/init.d/postgresql stop

COPY ./supervisor.conf /etc/openvas-supervisor.conf

VOLUME [ "/configs" ]
VOLUME [ "/targets" ]
VOLUME [ "/tasks" ]
VOLUME [ "/reports" ]
VOLUME [ "/overrides" ]
VOLUME [ "/filters" ]

EXPOSE 80 443

ENTRYPOINT [ "/entrypoint.py" ]
