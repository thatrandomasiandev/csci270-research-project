# Shared by the DIAMOND jobs. A non-absolute path stops the job.
# The message starts with STOP_INPUTS so it matches the Python checker.
require_absolute() {
  local name="$1"
  local value="$2"
  case "${value}" in
    /*) ;;
    *)
      echo "STOP_INPUTS: ${name} is not an absolute path: ${value}" >&2
      exit 2
      ;;
  esac
  printf '%s\n' "${value}"
}
