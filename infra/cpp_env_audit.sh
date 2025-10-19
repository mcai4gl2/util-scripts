#!/usr/bin/env bash
# cpp_env_audit.sh — inventory typical C++ toolchain/components
# Usage:
#   ./cpp_env_audit.sh [--json] [--brief]

set -euo pipefail
set -E
trap 'echo "[ERROR] line=$LINENO status=$? cmd=${BASH_COMMAND}" >&2' ERR

# Require Bash 4+ for associative arrays
if [ -z "${BASH_VERSINFO:-}" ] || [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "This script requires Bash 4+. Current: ${BASH_VERSION:-unknown}. Try: bash ./cpp_env_audit.sh" >&2
  exit 1
fi

want_json=0
want_brief=0
for a in "$@"; do
  case "$a" in
    --json) want_json=1 ;;
    --brief) want_brief=1 ;;
    *) echo "Unknown flag: $a" >&2; exit 2 ;;
  esac
done

# ---- helpers ---------------------------------------------------------------
have() { command -v "$1" >/dev/null 2>&1; }
first_nonempty() { for x in "$@"; do [ -n "${x:-}" ] && { echo "$x"; return; }; done; echo ""; }
kv() { printf "%-32s %s\n" "$1" "$2"; }

json_escape() {
  python3 - <<'PY' 2>/dev/null || sed -E 's/"/\\"/g'
import json,sys
print(json.dumps(sys.stdin.read().rstrip("\n")))
PY
}

put_item() { local key="$1"; shift; local val="${*:-}"; INVENTORY_KEYS+=("$key"); INVENTORY_VALS["$key"]="$val"; }

get_pkg_ver_dpkg() {
  local pattern="$1"
  if have dpkg-query; then
    { dpkg-query -W -f='${Package} ${Version}\n' "$pattern" 2>/dev/null || true; } | awk '{print $2}' | head -n1
  fi
}

get_lib_version_ldconfig() {
  local libpat="$1"
  if have ldconfig; then
    ldconfig -p 2>/dev/null | grep -E "$libpat" | head -n1 | sed -E 's/.*so(\.[0-9.]+).*/\1/' | sed 's/^\.//'
  fi
}

get_pkg_ver_pkgconfig() {
  local name="$1"
  if have pkg-config && pkg-config --exists "$name" 2>/dev/null; then
    pkg-config --modversion "$name" 2>/dev/null
  fi
}

grep_header_define() { # file, macro -> value
  local hdr="$1" macro="$2"
  [ -r "$hdr" ] || return 1
  awk -v M="$macro" '$1=="#define" && $2==M {for(i=3;i<=NF;i++) printf("%s%s",$i,(i<NF?" ":""));print ""}' "$hdr"
}

calc_asio_ver_from_int() { # e.g. 101800 -> 1.18.0
  local raw="$1"; [ -z "$raw" ] && return
  local major=$((raw/100000)); local minor=$(((raw/1000)%100)); local patch=$((raw%1000))
  echo "${major}.${minor}.${patch}"
}

# ---- inventory store -------------------------------------------------------
declare -a INVENTORY_KEYS=()
declare -A INVENTORY_VALS=()

# ---- OS / kernel / arch ----------------------------------------------------
os_name=""; os_ver=""
if [ -r /etc/os-release ]; then . /etc/os-release; os_name="${NAME:-}"; os_ver="${VERSION_ID:-$VERSION:-}"; fi
put_item "os.name"    "$(first_nonempty "$os_name" "$(uname -s)")"
put_item "os.version" "$(first_nonempty "$os_ver" "$(uname -r)")"
put_item "kernel.version" "$(uname -r)"
put_item "arch" "$(uname -m)"

# ---- Compilers & libc ------------------------------------------------------
gcc_ver=$(have gcc && gcc -dumpfullversion -dumpversion 2>/dev/null || true)
gpp_ver=$(have g++ && g++ -dumpfullversion -dumpversion 2>/dev/null || true)
clang_ver=$(have clang && clang --version 2>/dev/null | head -n1 | sed -E 's/.*clang version ([^ ]+).*/\1/' || true)
clangpp_ver=$(have clang++ && clang++ --version 2>/dev/null | head -n1 | sed -E 's/.*clang version ([^ ]+).*/\1/' || true)
put_item "compiler.gcc" "$gcc_ver"
put_item "compiler.g++" "$gpp_ver"
put_item "compiler.clang" "$clang_ver"
put_item "compiler.clang++" "$clangpp_ver"

if [ -n "${gpp_ver:-}" ]; then
  libstdcpp_path=$(g++ -print-file-name=libstdc++.so 2>/dev/null || true)
  if [ -n "$libstdcpp_path" ] && [ -r "$libstdcpp_path" ]; then
    glibcxx_tags=$(strings "$libstdcpp_path" | grep -Eo 'GLIBCXX_[0-9.]+' | sort -V | uniq | tail -n1)
    put_item "libstdc++.max_glibcxx" "$glibcxx_tags"
  fi
fi

glibc_ver=$( (ldd --version 2>/dev/null || true) | head -n1 | sed -E 's/.* ([0-9]+\.[0-9]+(\.[0-9]+)?).*/\1/' )
put_item "libc.glibc" "$glibc_ver"

# ---- Build tools -----------------------------------------------------------
put_item "cmake"        "$(have cmake && cmake --version | head -n1 | awk '{print $3}' || true)"
put_item "ninja"        "$(have ninja && ninja --version 2>/dev/null || true)"
put_item "make"         "$(have make  && make --version  | head -n1 | awk '{print $3}' || true)"
put_item "pkg-config"   "$(have pkg-config && pkg-config --version || true)"

# ---- Debug/profiling -------------------------------------------------------
put_item "gdb"          "$(have gdb   && gdb --version   | head -n1 | awk '{print $NF}' || true)"
put_item "lldb"         "$(have lldb  && lldb --version  | head -n1 | awk '{print $NF}' || true)"
put_item "valgrind"     "$(have valgrind && valgrind --version | awk '{print $2}' || true)"
put_item "perf"         "$(have perf  && perf --version 2>/dev/null | awk '{print $3}' || true)"

asan_support=""
if [ -n "${gpp_ver:-}" ]; then
  echo "" | g++ -x c++ - -fsyntax-only -fsanitize=address -o /dev/null >/dev/null 2>&1 && asan_support="yes" || asan_support="no"
fi
put_item "sanitizer.address" "$asan_support"

# ---- Core libraries --------------------------------------------------------
# Boost
boost_ver_pkgcfg=$(get_pkg_ver_pkgconfig "boost" || true)
boost_ver_header=$(grep_header_define "/usr/include/boost/version.hpp" "BOOST_LIB_VERSION" || true)
boost_ver_header=${boost_ver_header//\"/}; boost_ver_header=${boost_ver_header//_/\.}
boost_ver=$(first_nonempty "$boost_ver_pkgcfg" "$boost_ver_header" "$(get_pkg_ver_dpkg 'libboost-system*')")
put_item "boost.version" "$boost_ver"

# Asio (standalone)
asio_header="/usr/include/asio.hpp"
asio_vhdr="/usr/include/asio/version.hpp"
asio_ver=""
if [ -r "$asio_vhdr" ]; then
  raw=$(grep_header_define "$asio_vhdr" "ASIO_VERSION" || true)
  [ -n "$raw" ] && asio_ver="$(calc_asio_ver_from_int "$raw")"
fi
put_item "asio.standalone" "$( [ -r "$asio_header" ] && echo "present (${asio_ver:-unknown})" || echo "" )"
# Boost.Asio presence
put_item "asio.boost" "$( [ -r /usr/include/boost/asio.hpp ] && echo "present (boost ${boost_ver:-unknown})" || echo "" )"

# Common libs
put_item "openssl"   "$(have openssl && openssl version 2>/dev/null | awk '{print $2}' || true)"
put_item "zlib"      "$(get_pkg_ver_pkgconfig zlib || get_lib_version_ldconfig 'libz\.so' || true)"
put_item "libcurl"   "$(have curl && curl --version 2>/dev/null | head -n1 | awk '{print $2}' || get_pkg_ver_pkgconfig libcurl || true)"
put_item "protobuf"  "$(have protoc && protoc --version 2>/dev/null | awk '{print $2}' || get_pkg_ver_pkgconfig protobuf || true)"
put_item "fmt"       "$(get_pkg_ver_pkgconfig fmt || true)"
put_item "spdlog"    "$(get_pkg_ver_pkgconfig spdlog || true)"
put_item "gtest"     "$(get_pkg_ver_pkgconfig gtest || get_pkg_ver_dpkg 'libgtest*' || true)"
put_item "sqlite3"   "$(have sqlite3 && sqlite3 --version 2>/dev/null | awk '{print $1}' || get_pkg_ver_pkgconfig sqlite3 || true)"
put_item "libpq(postgres)" "$(have psql && psql --version 2>/dev/null | awk '{print $3}' || get_pkg_ver_pkgconfig libpq || true)"
put_item "mysqlclient"     "$(get_pkg_ver_pkgconfig mysqlclient || get_lib_version_ldconfig 'libmysqlclient\.so' || true)"

# Parallel/GPU
put_item "openmp(g++)" "$(
  if [ -n "${gpp_ver:-}" ]; then
    echo "" | g++ -x c++ - -fsyntax-only -fopenmp -o /dev/null >/dev/null 2>&1 && echo yes || echo no
  fi
)"
put_item "cuda.nvcc"   "$(have nvcc && nvcc --version 2>/dev/null | grep -Eo 'release[^,]+' | awk '{print $2}' || true)"

# ---- EXTRA LIBS ------------------------------------------------------------
# gRPC
grpc_ver="$( get_pkg_ver_pkgconfig grpc || true )"
[ -z "$grpc_ver" ] && grpc_ver="$( get_pkg_ver_pkgconfig grpc++ || true )"
[ -z "$grpc_ver" ] && grpc_ver="$( have grpc_cpp_plugin && grpc_cpp_plugin --version 2>/dev/null | awk '{print $NF}' || true )"
put_item "grpc" "$grpc_ver"

# Abseil
absl_ver="$( get_pkg_ver_pkgconfig absl_base || get_pkg_ver_pkgconfig absl_strings || true )"
if [ -z "$absl_ver" ]; then
  v=$(grep_header_define "/usr/include/absl/base/options.h" "ABSL_LTS_RELEASE_VERSION" || true)
  [ -z "$v" ] && v=$(grep_header_define "/usr/include/absl/base/config.h" "ABSL_LTS_RELEASE_VERSION" || true)
  v="${v//\"/}"
  [ -n "$v" ] && absl_ver="$v"
fi
put_item "abseil" "$absl_ver"

# Cap'n Proto
capnp_ver="$( get_pkg_ver_pkgconfig capnp || true )"
[ -z "$capnp_ver" ] && capnp_ver="$( have capnp && capnp --version 2>/dev/null | awk '{print $2}' || true )"
put_item "capnproto" "$capnp_ver"

# tcmalloc (gperftools)
tcmalloc_ver="$( get_pkg_ver_pkgconfig libtcmalloc || get_pkg_ver_pkgconfig libtcmalloc_minimal || get_pkg_ver_dpkg 'libtcmalloc*' || get_lib_version_ldconfig 'libtcmalloc(_minimal)?\.so' || true )"
put_item "tcmalloc" "$tcmalloc_ver"

# jemalloc
jemalloc_ver="$( get_pkg_ver_pkgconfig jemalloc || get_pkg_ver_dpkg 'libjemalloc*' || get_lib_version_ldconfig 'libjemalloc\.so' || true )"
put_item "jemalloc" "$jemalloc_ver"

# ZeroMQ
zmq_ver="$( get_pkg_ver_pkgconfig libzmq || get_pkg_ver_pkgconfig zmq || get_pkg_ver_dpkg 'libzmq*' || true )"
put_item "zeromq" "$zmq_ver"

# hiredis (Redis C client)
hiredis_ver="$( get_pkg_ver_pkgconfig hiredis || get_pkg_ver_dpkg 'libhiredis*' || get_lib_version_ldconfig 'libhiredis\.so' || true )"
put_item "hiredis" "$hiredis_ver"

# rdkafka (librdkafka)
rdkafka_ver="$( get_pkg_ver_pkgconfig rdkafka || get_pkg_ver_dpkg 'librdkafka*' || get_lib_version_ldconfig 'librdkafka\.so' || true )"
put_item "rdkafka" "$rdkafka_ver"

# fuse3
fuse3_ver="$( get_pkg_ver_pkgconfig fuse3 || get_pkg_ver_dpkg 'libfuse3-*' || get_lib_version_ldconfig 'libfuse3\.so' || true )"
put_item "fuse3" "$fuse3_ver"

# ---- Boost components present ---------------------------------------------
boost_libs=""
if have dpkg-query; then
  boost_libs=$({ dpkg-query -W -f='${Package}\n' 'libboost-*' 2>/dev/null || true; } | tr '\n' ' ' | sed 's/ *$//')
else
  boost_libs=$(ldconfig -p 2>/dev/null | grep -oE 'libboost_[a-z0-9_]+' | sort -u | tr '\n' ' ' | sed 's/ *$//')
fi
put_item "boost.components" "$boost_libs"

# ---- output ---------------------------------------------------------------
if [ "$want_json" -eq 1 ]; then
  echo '{'
  first=1
  for k in "${INVENTORY_KEYS[@]}"; do
    v="${INVENTORY_VALS["$k"]}"
    [ -z "$v" ] && continue
    [ $first -eq 0 ] && echo ','
    first=0
    printf '  "%s": ' "$k"
    printf '%s' "$(printf "%s" "$v" | json_escape)"
  done
  echo
  echo '}'
  exit 0
fi

echo "C++ Environment Inventory"
echo "================================================"
kv "OS"                 "${INVENTORY_VALS["os.name"]} ${INVENTORY_VALS["os.version"]}"
kv "Kernel"             "${INVENTORY_VALS["kernel.version"]}"
kv "Arch"               "${INVENTORY_VALS["arch"]}"

echo
echo "Compilers / Libc"
echo "------------------------------------------------"
kv "gcc"                "${INVENTORY_VALS["compiler.gcc"]}"
kv "g++"                "${INVENTORY_VALS["compiler.g++"]}"
kv "clang"              "${INVENTORY_VALS["compiler.clang"]}"
kv "clang++"            "${INVENTORY_VALS["compiler.clang++"]}"
kv "glibc"              "${INVENTORY_VALS["libc.glibc"]}"
kv "libstdc++ ABI"      "${INVENTORY_VALS["libstdc++.max_glibcxx"]}"

echo
echo "Build Tools"
echo "------------------------------------------------"
kv "cmake"              "${INVENTORY_VALS["cmake"]}"
kv "ninja"              "${INVENTORY_VALS["ninja"]}"
kv "make"               "${INVENTORY_VALS["make"]}"
kv "pkg-config"         "${INVENTORY_VALS["pkg-config"]}"

echo
echo "Debug / Profiling"
echo "------------------------------------------------"
kv "gdb"                "${INVENTORY_VALS["gdb"]}"
kv "lldb"               "${INVENTORY_VALS["lldb"]}"
kv "valgrind"           "${INVENTORY_VALS["valgrind"]}"
kv "perf"               "${INVENTORY_VALS["perf"]}"
kv "ASan support"       "${INVENTORY_VALS["sanitizer.address"]}"

echo
echo "Core Libraries"
echo "------------------------------------------------"
kv "Boost (core)"       "${INVENTORY_VALS["boost.version"]}"
kv "Boost.Asio"         "${INVENTORY_VALS["asio.boost"]}"
kv "Asio (standalone)"  "${INVENTORY_VALS["asio.standalone"]}"
kv "OpenSSL"            "${INVENTORY_VALS["openssl"]}"
kv "zlib"               "${INVENTORY_VALS["zlib"]}"
kv "libcurl"            "${INVENTORY_VALS["libcurl"]}"
kv "protobuf"           "${INVENTORY_VALS["protobuf"]}"
kv "fmt"                "${INVENTORY_VALS["fmt"]}"
kv "spdlog"             "${INVENTORY_VALS["spdlog"]}"
kv "gtest"              "${INVENTORY_VALS["gtest"]}"
kv "sqlite3"            "${INVENTORY_VALS["sqlite3"]}"
kv "Postgres libpq"     "${INVENTORY_VALS["libpq(postgres)"]}"
kv "MySQL client"       "${INVENTORY_VALS["mysqlclient"]}"

echo
echo "Parallel / GPU"
echo "------------------------------------------------"
kv "OpenMP (g++)"       "${INVENTORY_VALS["openmp(g++)"]}"
kv "CUDA (nvcc)"        "${INVENTORY_VALS["cuda.nvcc"]}"

echo
echo "Extra Libraries"
echo "------------------------------------------------"
kv "gRPC"               "${INVENTORY_VALS["grpc"]}"
kv "Abseil"             "${INVENTORY_VALS["abseil"]}"
kv "Cap'n Proto"        "${INVENTORY_VALS["capnproto"]}"
kv "tcmalloc"           "${INVENTORY_VALS["tcmalloc"]}"
kv "jemalloc"           "${INVENTORY_VALS["jemalloc"]}"
kv "ZeroMQ"             "${INVENTORY_VALS["zeromq"]}"
kv "hiredis"            "${INVENTORY_VALS["hiredis"]}"
kv "librdkafka"         "${INVENTORY_VALS["rdkafka"]}"
kv "FUSE3"              "${INVENTORY_VALS["fuse3"]}"

if [ "$want_brief" -eq 0 ]; then
  echo
  echo "Boost Components Present"
  echo "------------------------------------------------"
  echo "${INVENTORY_VALS["boost.components"]}"
fi
