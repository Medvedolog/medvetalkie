#ifndef MEDVETALKIE_STATE_H
#define MEDVETALKIE_STATE_H

#include <stdbool.h>

typedef enum {
    MT_HEADSET_UNASSIGNED = 0,
    MT_HEADSET_DISCONNECTED,
    MT_HEADSET_CONNECTING,
    MT_HEADSET_CONNECTED_NO_AUDIO,
    MT_HEADSET_PROFILE_PENDING,
    MT_HEADSET_HFP_READY,
    MT_HEADSET_A2DP_READY,
    MT_HEADSET_RECOVERING,
    MT_HEADSET_ERROR
} mt_headset_state;

typedef enum {
    MT_MODE_INTERCOM = 0,
    MT_MODE_SOLO_STEREO,
    MT_MODE_ANDROID_MEDIA,
    MT_MODE_ANDROID_BRIDGE_CALL,
    MT_MODE_PHONE_DIRECT
} mt_mode;

typedef struct {
    mt_headset_state headset1;
    mt_headset_state headset2;
    bool phone_a2dp_ready;
    bool phone_hfp_bridge_ready;
} mt_capabilities;

/* Pure capability gate, NOT proof of actual hardware readiness. */
bool mt_mode_prerequisites(mt_mode mode, const mt_capabilities *caps);
const char *mt_headset_state_name(mt_headset_state state);

#endif
