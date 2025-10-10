# syntax=docker/dockerfile:1.7
ARG BASE_IMG=debian:12
FROM ${BASE_IMG}

ARG DEBIAN_FRONTEND=noninteractive
ARG GCC_VER=13
ARG CLANG_VER=18

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates tzdata git curl wget file \
    build-essential gcc-${GCC_VER} g++-${GCC_VER} \
    clang-${CLANG_VER} lld-${CLANG_VER} \
    cmake ninja-build pkg-config \
    pciutils usbutils hwloc \
    ethtool iproute2 numactl linux-perf \
 && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-${GCC_VER} 100 || true && \
    update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-${GCC_VER} 100 || true && \
    update-alternatives --install /usr/bin/clang clang /usr/bin/clang-${CLANG_VER} 100 || true && \
    update-alternatives --install /usr/bin/ld ld.lld /usr/bin/ld.lld-${CLANG_VER} 100 || true

RUN useradd -ms /bin/bash vscode
USER vscode
WORKDIR /work

