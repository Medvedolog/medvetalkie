#include "medvetalkie/state.h"

bool mt_mode_prerequisites(mt_mode mode, const mt_capabilities *caps)
{
    if (!caps) return false;
    switch (mode) {
    case MT_MODE_INTERCOM:
        return caps->headset1 == MT_HEADSET_HFP_READY &&
               caps->headset2 == MT_HEADSET_HFP_READY;
    case MT_MODE_SOLO_STEREO:
        return caps->headset1 == MT_HEADSET_A2DP_READY ||
               caps->headset2 == MT_HEADSET_A2DP_READY;
    case MT_MODE_ANDROID_MEDIA:
        return caps->phone_a2dp_ready &&
               (caps->headset1 == MT_HEADSET_A2DP_READY ||
                caps->headset2 == MT_HEADSET_A2DP_READY);
    case MT_MODE_ANDROID_BRIDGE_CALL:
        return caps->phone_hfp_bridge_ready &&
               (caps->headset1 == MT_HEADSET_HFP_READY ||
                caps->headset2 == MT_HEADSET_HFP_READY);
    case MT_MODE_PHONE_DIRECT:
        return true; /* Actual release of headset is asynchronous. */
    default:
        return false;
    }
}

const char *mt_headset_state_name(mt_headset_state state)
{
    switch (state) {
    case MT_HEADSET_UNASSIGNED: return "UNASSIGNED";
    case MT_HEADSET_DISCONNECTED: return "DISCONNECTED";
    case MT_HEADSET_CONNECTING: return "CONNECTING";
    case MT_HEADSET_CONNECTED_NO_AUDIO: return "CONNECTED_NO_AUDIO";
    case MT_HEADSET_PROFILE_PENDING: return "PROFILE_PENDING";
    case MT_HEADSET_HFP_READY: return "HFP_READY";
    case MT_HEADSET_A2DP_READY: return "A2DP_READY";
    case MT_HEADSET_RECOVERING: return "RECOVERING";
    case MT_HEADSET_ERROR: return "ERROR";
    default: return "UNKNOWN";
    }
}
