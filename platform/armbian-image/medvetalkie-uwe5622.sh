#!/usr/bin/env bash
# @description MedveTalkie Orange Pi Zero 3: compile patched AW859A BSP/Wi-Fi
# and SDIO Bluetooth transport in the actual Armbian image chroot.
# Enabled explicitly by staged build; no automatic CP-assert recovery.
#
# Armbian built-in uwe5622-allwinner extension is retained for firmware,
# BlueZ, rfkill, hciattach_opi and the board's boot/DTB configuration.

function extension_finish_config__medvetalkie_headers() {
  if [[ "\${BOARD}" != orangepizero3 || "\${BRANCH}" != current || "\${RELEASE}" != trixie ]]; then
    exit_with_error "MedveTalkie profile supports only orangepizero3/current/trixie"
  fi
  if [[ "\${KERNEL_HAS_WORKING_HEADERS:-no}" != yes ]]; then
    exit_with_error "Target Armbian kernel does not offer working headers; refusing an unpatched image"
  fi
  declare -g INSTALL_HEADERS=yes
  display_alert "MedveTalkie: requiring exact target kernel headers" "INSTALL_HEADERS=yes" "info"
}

function post_install_kernel_debs__medvetalkie_modules() {
  [[ "\${INSTALL_HEADERS}" == yes ]] || exit_with_error "Missing Armbian headers"
  local target_kver="\${IMAGE_INSTALLED_KERNEL_VERSION}-\${BRANCH}-\${LINUXFAMILY}"
  local source_dir="\${SRC}/userpatches/medvetalkie-uwe5622-src"
  local installed="/usr/src/medvetalkie-uwe5622-1.0"
  [[ -s "\${source_dir}/BUILD-PROVENANCE.txt" ]] || exit_with_error "No staged, pinned MedveTalkie driver source"
  [[ -s "\${source_dir}/install-image-modules.sh" ]] || exit_with_error "No staged image module compiler"
  [[ -n "\${IMAGE_INSTALLED_KERNEL_VERSION:-}" ]] || exit_with_error "Image kernel version unavailable"

  display_alert "MedveTalkie: building all UWE5622 modules for \${target_kver}" "BSP/WLAN/BT" "info"
  use_clean_environment=yes chroot_sdcard_apt_get_install make gcc libc6-dev binutils kmod

  run_host_command_logged mkdir -p "\${SDCARD}\${installed}"
  run_host_command_logged cp -a "\${source_dir}/." "\${SDCARD}\${installed}/"
  declare -ag if_error_find_files_sdcard=("/usr/src/medvetalkie-uwe5622-1.0/**/*.log")
  use_clean_environment=yes chroot_sdcard "bash \${installed}/install-image-modules.sh '\${target_kver}'"
}

function post_family_tweaks__medvetalkie_safety_defaults() {
  local assets="\${SRC}/userpatches/medvetalkie-uwe5622-scripts"
  local root="\${SDCARD}"
  [[ -s "\${assets}/uwe5622-recover" ]] || exit_with_error "No MedveTalkie Wi-Fi recovery assets"
  install -d -m 755 "\${root}/usr/local/sbin" "\${root}/etc/systemd/system" \
    "\${root}/etc/systemd/system/aw859a-bluetooth.service.d"
  install -m 755 "\${assets}/uwe5622-recover" "\${root}/usr/local/sbin/uwe5622-recover"
  install -m 755 "\${assets}/uwe5622-preflight" "\${root}/usr/local/sbin/uwe5622-preflight"
  install -m 755 "\${assets}/uwe5622-abi-check" "\${root}/usr/local/sbin/uwe5622-abi-check"
  install -m 644 "\${assets}/medvetalkie-uwe5622-recover.service" \
    "\${root}/etc/systemd/system/medvetalkie-uwe5622-recover.service"
  # The upstream Armbian board extension enables the onboard BT attach unit.
  # Guard its activation to avoid conflicts with two USB UGREEN CM390 dongles.
  # This DOES NOT blacklist sprdbt_tty or disable BlueZ/USB Bluetooth.
  printf '[Unit]\nConditionPathExists=/etc/medvetalkie/enable-onboard-bluetooth\n' \
    > "\${root}/etc/systemd/system/aw859a-bluetooth.service.d/10-medvetalkie-opt-in.conf"
  display_alert "MedveTalkie: BT SDIO attach opt-in; USB BT and Wi-Fi unaffected" "safe defaults" "info"
}
