FROM ubuntu:bionic as build

ARG openvas_scanner="v6.0+beta2.tar.gz"
ARG gvm_libs="v1.0+beta2.tar.gz"
ARG gvmd="v8.0+beta2.tar.gz"
ARG gsa="v8.0+beta2.tar.gz"

ARG build_type="Debug"
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
      libsqlite3-dev \
      libical-dev \
      libmicrohttpd-dev \
      libxml2-dev \
      nodejs \
      python-polib \
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
    cmake ${cmake_build_params} .. && \
    make && \
    make DESTDIR=${install_dir} install

# Building gsa

RUN curl -O -L "https://github.com/greenbone/gsa/archive/${gsa}" && \
    tar -xvf ${gsa} && \
    cd gsa-8.0-* && \
    mkdir build && \
    cd build && \
    cmake ${cmake_build_params} .. && \
    make && \
    make DESTDIR=${install_dir} install && \
    mkdir -p ${install_dir}/${local_state_dir}/lib/openvas/gvmd/

FROM ubuntu:bionic

ARG python_gvm="==1.0.0b2"
ARG install_dir="/openvas"
ARG wait_sync="210"

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
      sqlite3 \
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

# Syncing NVT, CERT and SCAP data

RUN greenbone-nvt-sync && \
    sleep ${wait_sync}

RUN greenbone-certdata-sync && \
    sleep ${wait_sync}

RUN greenbone-scapdata-sync

RUN gvm-manage-certs -a && \
    gvmd -d /var/lib/openvas/gvmd/gvmd.db --create-user test && \
    gvmd -d /var/lib/openvas/gvmd/gvmd.db --delete-user test && \
    curl -O -L https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.xml && \
    gvm-portnames-update service-names-port-numbers.xml && \
    rm service-names-port-numbers.xml

COPY ./redis.conf /etc/openvas-redis.conf
COPY ./supervisor.conf /etc/openvas-supervisor.conf
COPY ./entrypoint.py /
COPY ./gvm_client.py /

RUN chmod +x /entrypoint.py /gvm_client.py

VOLUME [ "/configs" ]
VOLUME [ "/targets" ]
VOLUME [ "/tasks" ]
VOLUME [ "/reports" ]

EXPOSE 80 443

ENTRYPOINT [ "/entrypoint.py" ]
