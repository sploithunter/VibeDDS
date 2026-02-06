

/*
WARNING: THIS FILE IS AUTO-GENERATED. DO NOT MODIFY.

This file was generated from SimpleType.idl 
using RTI Code Generator (rtiddsgen) version 4.3.0.5.
The rtiddsgen tool is part of the RTI Connext DDS distribution.
For more information, type 'rtiddsgen -help' at a command shell
or consult the Code Generator User's Manual.
*/

#ifndef NDDS_STANDALONE_TYPE
#ifndef ndds_c_h
#include "ndds/ndds_c.h"
#endif

#ifndef dds_c_log_infrastructure_h
#include "dds_c/dds_c_infrastructure_impl.h"       
#endif 

#ifndef cdr_type_h
#include "cdr/cdr_type.h"
#endif    

#ifndef osapi_heap_h
#include "osapi/osapi_heap.h" 
#endif
#else
#include "ndds_standalone_type.h"
#endif

#include "SimpleType.h"

#ifndef NDDS_STANDALONE_TYPE
#include "SimpleTypePlugin.h"
#endif

/* ========================================================================= */
const char *SimpleTypeTYPENAME = "SimpleType";

#ifndef NDDS_STANDALONE_TYPE
DDS_TypeCode * SimpleType_get_typecode(void)
{
    static RTIBool is_initialized = RTI_FALSE;

    static DDS_TypeCode SimpleType_g_tc_message_string = DDS_INITIALIZE_STRING_TYPECODE((64L));

    static DDS_TypeCode_Member SimpleType_g_tc_members[4]=
    {

        {
            (char *)"message",/* Member name */
            {
                0,/* Representation ID */
                DDS_BOOLEAN_FALSE,/* Is a pointer? */
                -1, /* Bitfield bits */
                NULL/* Member type code is assigned later */
            },
            0, /* Ignored */
            0, /* Ignored */
            0, /* Ignored */
            NULL, /* Ignored */
            RTI_CDR_KEY_MEMBER , /* Is a key? */
            DDS_PUBLIC_MEMBER,/* Member visibility */
            1,
            NULL, /* Ignored */
            RTICdrTypeCodeAnnotations_INITIALIZER
        }, 
        {
            (char *)"x",/* Member name */
            {
                1,/* Representation ID */
                DDS_BOOLEAN_FALSE,/* Is a pointer? */
                -1, /* Bitfield bits */
                NULL/* Member type code is assigned later */
            },
            0, /* Ignored */
            0, /* Ignored */
            0, /* Ignored */
            NULL, /* Ignored */
            RTI_CDR_REQUIRED_MEMBER, /* Is a key? */
            DDS_PUBLIC_MEMBER,/* Member visibility */
            1,
            NULL, /* Ignored */
            RTICdrTypeCodeAnnotations_INITIALIZER
        }, 
        {
            (char *)"y",/* Member name */
            {
                2,/* Representation ID */
                DDS_BOOLEAN_FALSE,/* Is a pointer? */
                -1, /* Bitfield bits */
                NULL/* Member type code is assigned later */
            },
            0, /* Ignored */
            0, /* Ignored */
            0, /* Ignored */
            NULL, /* Ignored */
            RTI_CDR_REQUIRED_MEMBER, /* Is a key? */
            DDS_PUBLIC_MEMBER,/* Member visibility */
            1,
            NULL, /* Ignored */
            RTICdrTypeCodeAnnotations_INITIALIZER
        }, 
        {
            (char *)"count",/* Member name */
            {
                3,/* Representation ID */
                DDS_BOOLEAN_FALSE,/* Is a pointer? */
                -1, /* Bitfield bits */
                NULL/* Member type code is assigned later */
            },
            0, /* Ignored */
            0, /* Ignored */
            0, /* Ignored */
            NULL, /* Ignored */
            RTI_CDR_REQUIRED_MEMBER, /* Is a key? */
            DDS_PUBLIC_MEMBER,/* Member visibility */
            1,
            NULL, /* Ignored */
            RTICdrTypeCodeAnnotations_INITIALIZER
        }
    };

    static DDS_TypeCode SimpleType_g_tc =
    {{
            DDS_TK_STRUCT, /* Kind */
            DDS_BOOLEAN_FALSE, /* Ignored */
            -1, /*Ignored*/
            (char *)"SimpleType", /* Name */
            NULL, /* Ignored */      
            0, /* Ignored */
            0, /* Ignored */
            NULL, /* Ignored */
            4, /* Number of members */
            SimpleType_g_tc_members, /* Members */
            DDS_VM_NONE, /* Ignored */
            RTICdrTypeCodeAnnotations_INITIALIZER,
            DDS_BOOLEAN_TRUE, /* _isCopyable */
            NULL, /* _sampleAccessInfo: assigned later */
            NULL /* _typePlugin: assigned later */
        }}; /* Type code for SimpleType*/

    if (is_initialized) {
        return &SimpleType_g_tc;
    }

    is_initialized = RTI_TRUE;

    SimpleType_g_tc._data._annotations._allowedDataRepresentationMask = 5;

    SimpleType_g_tc_members[0]._representation._typeCode = (RTICdrTypeCode *)&SimpleType_g_tc_message_string;
    SimpleType_g_tc_members[1]._representation._typeCode = (RTICdrTypeCode *)&DDS_g_tc_long;
    SimpleType_g_tc_members[2]._representation._typeCode = (RTICdrTypeCode *)&DDS_g_tc_long;
    SimpleType_g_tc_members[3]._representation._typeCode = (RTICdrTypeCode *)&DDS_g_tc_long;

    /* Initialize the values for member annotations. */
    SimpleType_g_tc_members[0]._annotations._defaultValue._d = RTI_XCDR_TK_STRING;
    SimpleType_g_tc_members[0]._annotations._defaultValue._u.string_value = (DDS_Char *) "";
    SimpleType_g_tc_members[1]._annotations._defaultValue._d = RTI_XCDR_TK_LONG;
    SimpleType_g_tc_members[1]._annotations._defaultValue._u.long_value = 0;
    SimpleType_g_tc_members[1]._annotations._minValue._d = RTI_XCDR_TK_LONG;
    SimpleType_g_tc_members[1]._annotations._minValue._u.long_value = RTIXCdrLong_MIN;
    SimpleType_g_tc_members[1]._annotations._maxValue._d = RTI_XCDR_TK_LONG;
    SimpleType_g_tc_members[1]._annotations._maxValue._u.long_value = RTIXCdrLong_MAX;
    SimpleType_g_tc_members[2]._annotations._defaultValue._d = RTI_XCDR_TK_LONG;
    SimpleType_g_tc_members[2]._annotations._defaultValue._u.long_value = 0;
    SimpleType_g_tc_members[2]._annotations._minValue._d = RTI_XCDR_TK_LONG;
    SimpleType_g_tc_members[2]._annotations._minValue._u.long_value = RTIXCdrLong_MIN;
    SimpleType_g_tc_members[2]._annotations._maxValue._d = RTI_XCDR_TK_LONG;
    SimpleType_g_tc_members[2]._annotations._maxValue._u.long_value = RTIXCdrLong_MAX;
    SimpleType_g_tc_members[3]._annotations._defaultValue._d = RTI_XCDR_TK_LONG;
    SimpleType_g_tc_members[3]._annotations._defaultValue._u.long_value = 0;
    SimpleType_g_tc_members[3]._annotations._minValue._d = RTI_XCDR_TK_LONG;
    SimpleType_g_tc_members[3]._annotations._minValue._u.long_value = RTIXCdrLong_MIN;
    SimpleType_g_tc_members[3]._annotations._maxValue._d = RTI_XCDR_TK_LONG;
    SimpleType_g_tc_members[3]._annotations._maxValue._u.long_value = RTIXCdrLong_MAX;

    SimpleType_g_tc._data._sampleAccessInfo =
    SimpleType_get_sample_access_info();
    SimpleType_g_tc._data._typePlugin =
    SimpleType_get_type_plugin_info();    

    return &SimpleType_g_tc;
}

RTIXCdrSampleAccessInfo *SimpleType_get_sample_access_info()
{
    static RTIBool is_initialized = RTI_FALSE;

    static RTIXCdrMemberAccessInfo SimpleType_g_memberAccessInfos[4] =
    {RTIXCdrMemberAccessInfo_INITIALIZER};

    static RTIXCdrSampleAccessInfo SimpleType_g_sampleAccessInfo = 
    RTIXCdrSampleAccessInfo_INITIALIZER;

    if (is_initialized) {
        return (RTIXCdrSampleAccessInfo*) &SimpleType_g_sampleAccessInfo;
    }

    SimpleType_g_memberAccessInfos[0].bindingMemberValueOffset[0] =
    offsetof(struct SimpleType, message);

    SimpleType_g_memberAccessInfos[1].bindingMemberValueOffset[0] =
    offsetof(struct SimpleType, x);

    SimpleType_g_memberAccessInfos[2].bindingMemberValueOffset[0] =
    offsetof(struct SimpleType, y);

    SimpleType_g_memberAccessInfos[3].bindingMemberValueOffset[0] =
    offsetof(struct SimpleType, count);

    SimpleType_g_sampleAccessInfo.memberAccessInfos = 
    SimpleType_g_memberAccessInfos;

    {
        size_t candidateTypeSize = sizeof(SimpleType);

        if (candidateTypeSize > RTIXCdrLong_MAX) {
            SimpleType_g_sampleAccessInfo.typeSize[0] =
            RTIXCdrLong_MAX;
        } else {
            SimpleType_g_sampleAccessInfo.typeSize[0] =
            (RTIXCdrUnsignedLong) candidateTypeSize;
        }
    }

    SimpleType_g_sampleAccessInfo.languageBinding = 
    RTI_XCDR_TYPE_BINDING_C ;

    is_initialized = RTI_TRUE;
    return (RTIXCdrSampleAccessInfo*) &SimpleType_g_sampleAccessInfo;
}
RTIXCdrTypePlugin *SimpleType_get_type_plugin_info()
{
    static RTIXCdrTypePlugin SimpleType_g_typePlugin = 
    {
        NULL, /* serialize */
        NULL, /* serialize_key */
        NULL, /* deserialize_sample */
        NULL, /* deserialize_key_sample */
        NULL, /* skip */
        NULL, /* get_serialized_sample_size */
        NULL, /* get_serialized_sample_max_size_ex */
        NULL, /* get_serialized_key_max_size_ex */
        NULL, /* get_serialized_sample_min_size */
        NULL, /* serialized_sample_to_key */
        (RTIXCdrTypePluginInitializeSampleFunction) 
        SimpleType_initialize_ex,
        NULL,
        (RTIXCdrTypePluginFinalizeSampleFunction)
        SimpleType_finalize_w_return,
        NULL,
        NULL
    };

    return &SimpleType_g_typePlugin;
}
#endif

RTIBool SimpleType_initialize(
    SimpleType* sample)
{
    return SimpleType_initialize_ex(
        sample, 
        RTI_TRUE, 
        RTI_TRUE);
}
RTIBool SimpleType_initialize_w_params(
    SimpleType *sample,
    const struct DDS_TypeAllocationParams_t *allocParams)
{

    if (sample == NULL) {
        return RTI_FALSE;
    }
    if (allocParams == NULL) {
        return RTI_FALSE;
    }

    if (allocParams->allocate_memory) {
        sample->message = DDS_String_alloc((64L));
        if (sample->message != NULL) {
            RTIOsapiUtility_unusedReturnValue(
                RTICdrType_copyStringEx(
                    &sample->message,
                    "",
                    (64L),
                    RTI_FALSE),
                    RTIBool);
        }
        if (sample->message == NULL) {
            return RTI_FALSE;
        }
    } else {
        if (sample->message != NULL) {
            RTIOsapiUtility_unusedReturnValue(
                RTICdrType_copyStringEx(
                    &sample->message,
                    "",
                    (64L),
                    RTI_FALSE),
                    RTIBool);
            if (sample->message == NULL) {
                return RTI_FALSE;
            }
        }
    }

    sample->x = 0;

    sample->y = 0;

    sample->count = 0;

    return RTI_TRUE;
}
RTIBool SimpleType_initialize_ex(
    SimpleType *sample,
    RTIBool allocatePointers, 
    RTIBool allocateMemory)
{

    struct DDS_TypeAllocationParams_t allocParams =
    DDS_TYPE_ALLOCATION_PARAMS_DEFAULT;

    allocParams.allocate_pointers =  (DDS_Boolean)allocatePointers;
    allocParams.allocate_memory = (DDS_Boolean)allocateMemory;

    return SimpleType_initialize_w_params(
        sample,
        &allocParams);
}

RTIBool SimpleType_finalize_w_return(
    SimpleType* sample)
{
    SimpleType_finalize_ex(sample, RTI_TRUE);

    return RTI_TRUE;
}

void SimpleType_finalize(
    SimpleType* sample)
{  
    SimpleType_finalize_ex(
        sample, 
        RTI_TRUE);
}

void SimpleType_finalize_ex(
    SimpleType *sample,
    RTIBool deletePointers)
{
    struct DDS_TypeDeallocationParams_t deallocParams =
    DDS_TYPE_DEALLOCATION_PARAMS_DEFAULT;

    if (sample==NULL) {
        return;
    } 

    deallocParams.delete_pointers = (DDS_Boolean)deletePointers;

    SimpleType_finalize_w_params(
        sample,
        &deallocParams);
}

void SimpleType_finalize_w_params(
    SimpleType *sample,
    const struct DDS_TypeDeallocationParams_t *deallocParams)
{
    if (sample==NULL) {
        return;
    }

    if (deallocParams == NULL) {
        return;
    }

    if (sample->message != NULL) {
        DDS_String_free(sample->message);
        sample->message=NULL;

    }

}

void SimpleType_finalize_optional_members(
    SimpleType* sample, RTIBool deletePointers)
{
    struct DDS_TypeDeallocationParams_t deallocParamsTmp =
    DDS_TYPE_DEALLOCATION_PARAMS_DEFAULT;
    struct DDS_TypeDeallocationParams_t * deallocParams =
    &deallocParamsTmp;

    if (sample==NULL) {
        return;
    } 
    if (deallocParams) {} /* To avoid warnings */

    deallocParamsTmp.delete_pointers = (DDS_Boolean)deletePointers;
    deallocParamsTmp.delete_optional_members = DDS_BOOLEAN_TRUE;

}

RTIBool SimpleType_copy(
    SimpleType* dst,
    const SimpleType* src)
{

    if (dst == NULL || src == NULL) {
        return RTI_FALSE;
    }

    if (!RTICdrType_copyStringEx (
        &dst->message
        ,
        src->message, 
        (64L) + 1,
        RTI_FALSE)){
        return RTI_FALSE;
    }
    if (!RTICdrType_copyLong (
        &dst->x, 
        &src->x)) { 
        return RTI_FALSE;
    }
    if (!RTICdrType_copyLong (
        &dst->y, 
        &src->y)) { 
        return RTI_FALSE;
    }
    if (!RTICdrType_copyLong (
        &dst->count, 
        &src->count)) { 
        return RTI_FALSE;
    }

    return RTI_TRUE;
}

/**
* <<IMPLEMENTATION>>
*
* Defines:  TSeq, T
*
* Configure and implement 'SimpleType' sequence class.
*/
#define T SimpleType
#define TSeq SimpleTypeSeq

#define T_initialize_w_params SimpleType_initialize_w_params

#define T_finalize_w_params   SimpleType_finalize_w_params
#define T_copy       SimpleType_copy

#ifndef NDDS_STANDALONE_TYPE
#include "dds_c/generic/dds_c_sequence_TSeq.gen"
#else
#include "dds_c_sequence_TSeq.gen"
#endif

#undef T_copy
#undef T_finalize_w_params

#undef T_initialize_w_params

#undef TSeq
#undef T

