# syntax=docker/dockerfile:1
#
# Builds the briancunningham6/FreeCAD fork headless.
# The CadClaude worker module (src/Mod/CadClaude/) is included automatically
# via the cmake INSTALL rule in src/Mod/CadClaude/CMakeLists.txt.
#
# Local build:
#   docker buildx build --platform linux/amd64 -t freecad-cadclaude:amd64 .
#   docker buildx build --platform linux/arm64 -t freecad-cadclaude:arm64 .
#
# For Apple Silicon (M1/M2/M3/M4) Mac / ARM64 Host:
#
#   docker buildx build --platform linux/arm64 -t freecad-cadclaude:arm64 --load .
#
# For Intel/AMD Processor / AMD64 Host:
#
#   docker buildx build --platform linux/amd64 -t freecad-cadclaude:amd64 --load .
#
# If no platform is specified, it will automatically build for the host target OS and architecture:
#   docker build -t freecad-cadclaude .
#
# The GitHub Actions workflow (build-docker.yml) builds natively on AMD64 runners.

FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

# Apply CVE patches from the base image, then install headless build deps.
# Qt6 headers are required by FreeCAD's cmake even for headless builds
# (App framework uses Qt signals/slots throughout).
# No Coin3D, GUI workbenches, or full Qt GUI stack.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    gnupg \
    cmake \
    curl \
    wget \
    htop \
    ninja-build \
    git \
    python3-dev \
    python3-pybind11 \
    qt6-base-dev \
    libboost-dev \
    libboost-date-time-dev \
    libboost-filesystem-dev \
    libboost-iostreams-dev \
    libboost-program-options-dev \
    libboost-python-dev \
    libboost-regex-dev \
    libboost-serialization-dev \
    libboost-thread-dev \
    libeigen3-dev \
    libxerces-c-dev \
    libocct-data-exchange-dev \
    libocct-ocaf-dev \
    libocct-visualization-dev \
    libyaml-cpp-dev \
    libzipios++-dev \
    libfmt-dev \
    libgomp1 \
    python3-lark \
    python3-packaging \
    swig \
    libicu-dev \
    zlib1g-dev \
    qt6-l10n-tools \
    qt6-tools-dev \
    libtbb-dev \
    libfreetype-dev \
    libharfbuzz-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 22+ using official NodeSource binary distributions
RUN mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY . /src/

RUN cmake -S /src -B /build \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/opt/freecad \
    \
    -DBUILD_GUI=OFF \
    \
    -DBUILD_PART=ON \
    -DBUILD_PART_DESIGN=ON \
    -DBUILD_SKETCHER=ON \
    -DBUILD_MATERIAL=ON \
    \
    -DBUILD_MESH=OFF \
    -DBUILD_MESH_PART=OFF \
    -DBUILD_FLAT_MESH=OFF \
    -DBUILD_FEM=OFF \
    -DBUILD_FEM_NETGEN=OFF \
    -DBUILD_ASSEMBLY=OFF \
    -DBUILD_CAM=OFF \
    -DBUILD_ADDONMGR=OFF \
    -DBUILD_ARCH=OFF \
    -DBUILD_BIM=OFF \
    -DBUILD_DRAFT=OFF \
    -DBUILD_HELP=OFF \
    -DBUILD_IMPORT=OFF \
    -DBUILD_INSPECTION=OFF \
    -DBUILD_MEASURE=OFF \
    -DBUILD_OPENSCAD=OFF \
    -DBUILD_PATH=OFF \
    -DBUILD_PLOT=OFF \
    -DBUILD_POINTS=OFF \
    -DBUILD_REVERSEENGINEERING=OFF \
    -DBUILD_ROBOT=OFF \
    -DBUILD_SHIP=OFF \
    -DBUILD_SHOW=OFF \
    -DBUILD_SPREADSHEET=OFF \
    -DBUILD_START=OFF \
    -DBUILD_SURFACE=OFF \
    -DBUILD_TECHDRAW=OFF \
    -DBUILD_TEST=OFF \
    -DBUILD_TUX=OFF \
    -DBUILD_WEB=OFF \
    -DFREECAD_USE_FREETYPE=ON \
    -DENABLE_DEVELOPER_TESTS=OFF

RUN cmake --build /build --parallel "$(nproc)"
RUN cmake --install /build

# ── FEM runtime dependencies ─────────────────────────────────────────────────
# CalculiX: FEM solver invoked as `ccx` subprocess by the FEM analysis script.
# python3-pip + system OpenGL: needed for gmsh and pyvista render dependencies.
# python3-gmsh and python3-vtk9: installed via system package manager as arm64 wheels
# for gmsh and vtk (version < 9.4) are not officially provided on PyPI.
RUN apt-get update && apt-get install -y --no-install-recommends \
    calculix-ccx \
    python3-pip \
    python3-gmsh \
    python3-vtk9 \
    libgl1 \
    libglu1-mesa \
    libegl1 \
    && rm -rf /var/lib/apt/lists/*

# gmsh + vtk: installed above via apt to support all platforms including arm64
# pyvista + numpy: FEM result rendering dependencies
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    "pyvista>=0.43,<0.44" \
    numpy

# Verify all dynamic links resolve. Any "not found" line fails the build
# rather than producing a broken image that fails silently at runtime.
RUN ldd /opt/freecad/bin/FreeCADCmd \
    | grep "not found" \
    | (grep . && echo "ERROR: missing shared libraries — add them to the apt list" && exit 1 || true)

ENV PATH=/opt/freecad/bin:$PATH
ENV LD_LIBRARY_PATH=/opt/freecad/lib

# FEM render: pyvista offscreen mode on headless Linux
ENV PYVISTA_OFF_SCREEN=true
# Render subprocess uses this Python (has pyvista, vtk, numpy installed above)
ENV RENDER_PYTHON_PATH=/usr/bin/python3

# Smoke-test: FreeCAD must start and print its version without errors.
RUN FreeCADCmd --version

CMD ["FreeCADCmd"]
