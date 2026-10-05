/**
 * AMR-NB 解码器的实现（调用内嵌的 opencore-amr）
 */
#include "amrnb_dec.h"

#include <stddef.h>

#include "frame_type_3gpp.h"
#include "sp_dec.h"
#include "amrdecode.h"

void* tieba_amrnb_create(void)
{
    static char decoder_id[] = "TiebaDesktop";
    void* state = NULL;

    if (GSMInitDecode(&state, (Word8*)decoder_id) != 0)
    {
        return NULL;
    }

    return state;
}

void tieba_amrnb_destroy(void* state)
{
    if (state != NULL)
    {
        void* decoder_state = state;
        GSMDecodeFrameExit(&decoder_state);
    }
}

int tieba_amrnb_decode(void* state, const uint8_t* frame, int frame_bytes, int16_t* out)
{
    unsigned int frame_type;

    if (state == NULL || frame == NULL || out == NULL || frame_bytes < 1)
    {
        return -1;
    }

    /* TOC 的高 4 位是帧类型，其余部分是压缩数据 */
    frame_type = (unsigned int)((frame[0] >> 3) & 0x0F);
    AMRDecode(state, (enum Frame_Type_3GPP)frame_type, (UWord8*)(frame + 1),
              (Word16*)out, MIME_IETF);

    return TIEBA_AMRNB_FRAME_SAMPLES;
}