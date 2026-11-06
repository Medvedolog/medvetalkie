#include "medvetalkie/state.h"
#include <assert.h>
#include <string.h>

int main(void)
{
    mt_capabilities c = {0};
    assert(!mt_mode_prerequisites(MT_MODE_INTERCOM, &c));
    c.headset1 = MT_HEADSET_CONNECTED_NO_AUDIO;
    c.headset2 = MT_HEADSET_HFP_READY;
    assert(!mt_mode_prerequisites(MT_MODE_INTERCOM, &c));
    c.headset1 = MT_HEADSET_HFP_READY;
    assert(mt_mode_prerequisites(MT_MODE_INTERCOM, &c));
    assert(!mt_mode_prerequisites(MT_MODE_SOLO_STEREO, &c));
    c.headset1 = MT_HEADSET_A2DP_READY;
    assert(mt_mode_prerequisites(MT_MODE_SOLO_STEREO, &c));
    assert(!mt_mode_prerequisites(MT_MODE_ANDROID_MEDIA, &c));
    c.phone_a2dp_ready = true;
    assert(mt_mode_prerequisites(MT_MODE_ANDROID_MEDIA, &c));
    assert(mt_mode_prerequisites(MT_MODE_PHONE_DIRECT, &c));
    assert(!mt_mode_prerequisites((mt_mode)99, &c));
    assert(!mt_mode_prerequisites(MT_MODE_INTERCOM, 0));
    assert(strcmp(mt_headset_state_name(MT_HEADSET_HFP_READY), "HFP_READY") == 0);
    return 0;
}
