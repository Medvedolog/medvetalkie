#!/usr/bin/env bash
# @description MedveTalkie Orange Pi Zero 3: compile patched AW859A BSP/Wi-Fi
# and SDIO Bluetooth transport in the actual Armbian image chroot.
# Enabled explicitly by staged build; no automatic CP-assert recovery.
#
function extension_prepare_config__medvetalkie_network() {
  if [[ "${NETWORKING_STACK}" != "network-manager" ]]; then
    exit_with_error "MedveTalkie image requires NETWORKING_STACK=network-manager"
  fi
  # NetworkManager shared mode uses dnsmasq for DHCP/DNS on each isolated subnet.
  add_packages_to_image dnsmasq-base
}

# Armbian's pinned sunxi 6.18 tree already contains this RTC fix. Its
# patch file is still shipped in the same patch directory, and the Python
# patcher correctly rejects a reverse/already-applied hunk. Skip ONLY that
# exact patch, and ONLY after validating both the base source and patch payload.
function kernel_extra_create_patches__medvetalkie_rtc_patch_guard() {
  local patch_file="${SRC}/patch/kernel/${KERNELPATCHDIR}/patches.armbian/drv-rtc-pcf8563-pass-driver-data-to-irq-handler.patch"
  local source_file="${kernel_work_dir}/drivers/rtc/rtc-pcf8563.c"

  [[ -f "${patch_file}" ]] || return 0
  [[ -s "${source_file}" ]] || exit_with_error "MedveTalkie RTC guard: kernel source file missing" "${source_file}"

  if grep -Fq 'pcf8563_driver.driver.name, pcf8563);' "${source_file}"; then
    if grep -Fq 'pcf8563_driver.driver.name, client);' "${source_file}"; then
      exit_with_error "MedveTalkie RTC guard: source contains both old and fixed dev_id calls"
    fi
    grep -Fq 'pcf8563_driver.driver.name, pcf8563);' "${patch_file}" || \
      exit_with_error "MedveTalkie RTC guard: unexpected RTC patch payload" "${patch_file}"
    grep -Fq 'pcf8563_driver.driver.name, client);' "${patch_file}" || \
      exit_with_error "MedveTalkie RTC guard: expected old dev_id hunk missing" "${patch_file}"

    local series_file="${SRC}/patch/kernel/${KERNELPATCHDIR}/series.conf"
    local series_entry="patches.armbian/${patch_file##*/}"
    local series_tmp
    [[ -s "${series_file}" ]] || exit_with_error "MedveTalkie RTC guard: series.conf missing" "${series_file}"
    local series_matches
    series_matches=$(awk -v target="${series_entry}" '$1 == target { n++ } END { print n+0 }' "${series_file}")
    [[ "${series_matches}" == 1 ]] || \
      exit_with_error "MedveTalkie RTC guard: expected exactly one series entry" "${series_file}"
    series_tmp="$(mktemp "${series_file}.XXXXXX")"
    if ! awk -v target="${series_entry}" '
      $1 == target { removed++; next }
      { print }
      END { if (removed != 1) exit 1 }
    ' "${series_file}" > "${series_tmp}"; then
      rm -f "${series_tmp}"
      exit_with_error "MedveTalkie RTC guard: expected exactly one series.conf entry" "${series_file}"
    fi
    cat "${series_tmp}" > "${series_file}"
    rm -f "${series_tmp}"
    rm -- "${patch_file}"
    display_alert "MedveTalkie: skipped duplicate upstream RTC fix and exact series entry" "verified pcf8563 dev_id already correct" "info"
  else
    display_alert "MedveTalkie: RTC fix not present in base source" "keeping Armbian patch enabled" "info"
  fi
}
# Armbian built-in uwe5622-allwinner extension is retained for firmware,
# BlueZ, rfkill, hciattach_opi and the board's boot/DTB configuration.

function extension_finish_config__medvetalkie_headers() {
  if [[ "${BOARD}" != orangepizero3 || "${BRANCH}" != current || "${RELEASE}" != trixie ]]; then
    exit_with_error "MedveTalkie profile supports only orangepizero3/current/trixie"
  fi
  if [[ "${KERNEL_HAS_WORKING_HEADERS:-no}" != yes ]]; then
    exit_with_error "Target Armbian kernel does not offer working headers; refusing an unpatched image"
  fi
  declare -g INSTALL_HEADERS=yes
  display_alert "MedveTalkie: requiring exact target kernel headers" "INSTALL_HEADERS=yes" "info"
}

function post_install_kernel_debs__medvetalkie_modules() {
  [[ "${INSTALL_HEADERS}" == yes ]] || exit_with_error "Missing Armbian headers"
  local target_kver="${IMAGE_INSTALLED_KERNEL_VERSION}-${BRANCH}-${LINUXFAMILY}"
  local source_dir="${SRC}/userpatches/medvetalkie-uwe5622-src"
  local installed="/usr/src/medvetalkie-uwe5622-1.0"
  [[ -s "${source_dir}/BUILD-PROVENANCE.txt" ]] || exit_with_error "No staged, pinned MedveTalkie driver source"
  [[ -s "${source_dir}/install-image-modules.sh" ]] || exit_with_error "No staged image module compiler"
  [[ -n "${IMAGE_INSTALLED_KERNEL_VERSION:-}" ]] || exit_with_error "Image kernel version unavailable"

  display_alert "MedveTalkie: building all UWE5622 modules for ${target_kver}" "BSP/WLAN/BT" "info"
  use_clean_environment=yes chroot_sdcard_apt_get_install make gcc libc6-dev binutils kmod

  run_host_command_logged mkdir -p "${SDCARD}${installed}"
  run_host_command_logged cp -a "${source_dir}/." "${SDCARD}${installed}/"
  declare -ag if_error_find_files_sdcard=("/usr/src/medvetalkie-uwe5622-1.0/**/*.log")
  use_clean_environment=yes chroot_sdcard "bash ${installed}/install-image-modules.sh '${target_kver}'"
}

function post_family_tweaks__medvetalkie_safety_defaults() {
  local assets="${SRC}/userpatches/medvetalkie-uwe5622-scripts"
  local network="${SRC}/userpatches/medvetalkie-network"
  local docs="${SRC}/userpatches/medvetalkie-docs"
  local root="${SDCARD}"
  [[ -s "${assets}/uwe5622-recover" ]] || exit_with_error "No MedveTalkie Wi-Fi recovery assets"
  [[ -s "${assets}/medvetalkie-bt-diagnose" ]] || exit_with_error "No passive Bluetooth inventory script"
  [[ -s "${network}/10-medvetalkie-ethernet.nmconnection" ]] || exit_with_error "No Ethernet profile"
  [[ -s "${network}/20-medvetalkie-wifi-ap.nmconnection" ]] || exit_with_error "No Wi-Fi AP profile"
  [[ -x "${root}/usr/sbin/NetworkManager" ]] || exit_with_error "NetworkManager package is missing"
  [[ -x "${root}/usr/sbin/dnsmasq" ]] || exit_with_error "dnsmasq-base package is missing"
  install -d -m 755 "${root}/usr/local/sbin" "${root}/etc/systemd/system" \
    "${root}/etc/systemd/system/aw859a-bluetooth.service.d" \
    "${root}/etc/NetworkManager/system-connections" \
    "${root}/etc/modules-load.d" "${root}/usr/local/sbin" \
    "${root}/usr/share/doc/medvetalkie"
  install -m 755 "${assets}/uwe5622-recover" "${root}/usr/local/sbin/uwe5622-recover"
  install -m 755 "${assets}/uwe5622-preflight" "${root}/usr/local/sbin/uwe5622-preflight"
  install -m 755 "${assets}/uwe5622-abi-check" "${root}/usr/local/sbin/uwe5622-abi-check"
  install -m 644 "${assets}/medvetalkie-uwe5622-recover.service" \
    "${root}/etc/systemd/system/medvetalkie-uwe5622-recover.service"
  install -m 600 "${network}/10-medvetalkie-ethernet.nmconnection" \
    "${root}/etc/NetworkManager/system-connections/10-medvetalkie-ethernet.nmconnection"
  install -m 600 "${network}/20-medvetalkie-wifi-ap.nmconnection" \
    "${root}/etc/NetworkManager/system-connections/20-medvetalkie-wifi-ap.nmconnection"
  install -m 755 "${network}/medvetalkie-network-check" \
    "${root}/usr/local/sbin/medvetalkie-network-check"
  install -m 755 "${assets}/medvetalkie-bt-diagnose" \
    "${root}/usr/local/sbin/medvetalkie-bt-diagnose"
  install -m 644 "${network}/medvetalkie-usb-bt.service" \
    "${root}/etc/systemd/system/medvetalkie-usb-bt.service"
  printf "btusb\\n" > "${root}/etc/modules-load.d/medvetalkie-bt.conf"
  chmod 644 "${root}/etc/modules-load.d/medvetalkie-bt.conf"
  cp -a "${docs}/." "${root}/usr/share/doc/medvetalkie/"
  chown -R 0:0 "${root}/etc/NetworkManager/system-connections" \
    "${root}/etc/modules-load.d/medvetalkie-bt.conf" \
    "${root}/etc/systemd/system/medvetalkie-usb-bt.service"
  # The upstream Armbian board extension enables the onboard BT attach unit.
  # Guard its activation to avoid conflicts with two USB UGREEN CM390 dongles.
  # This DOES NOT blacklist sprdbt_tty or disable BlueZ/USB Bluetooth.
  printf '[Unit]\nConditionPathExists=/etc/medvetalkie/enable-onboard-bluetooth\n' \
    > "${root}/etc/systemd/system/aw859a-bluetooth.service.d/10-medvetalkie-opt-in.conf"
  chroot_sdcard systemctl enable NetworkManager.service bluetooth.service medvetalkie-usb-bt.service || \
    exit_with_error "Failed to enable NetworkManager/BlueZ USB Bluetooth services"
  display_alert "MedveTalkie: NetworkManager LAN/AP and two USB btusb adapters configured" "first boot" "info"
  display_alert "MedveTalkie: onboard BT attach remains opt-in; USB BT and Wi-Fi preserved" "safe defaults" "info"
}
