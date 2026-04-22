
#ifndef __CPU_PRED_STATIC_PRED_HH__
#define __CPU_PRED_STATIC_PRED_HH__

#include <vector>

// #include "base/sat_counter.hh"
#include "base/types.hh"
#include "cpu/pred/conditional.hh"
#include "cpu/pred/indirect.hh"
#include "params/StaticBP.hh"
#include "params/StaticIndirectBP.hh"

namespace gem5
{

namespace branch_prediction
{

/**
 * Implements a local predictor that uses the PC to index into a table of
 * counters.  Note that any time a pointer to the bp_history is given, it
 * should be NULL using this predictor because it does not have any branch
 * predictor state that needs to be recorded or updated; the update can be
 * determined solely by the branch being taken or not taken.
 */
class StaticBP : public ConditionalPredictor
{
  public:
    /**
     * Default branch predictor constructor.
     */
    StaticBP(const StaticBPParams &params);

    // Overriding interface functions
    bool lookup(ThreadID tid, Addr pc, void *&bp_history) override;

    void
    branchPlaceholder(ThreadID tid, Addr pc, bool uncond,
                      void *&bp_history) override
    {
        // Placeholder
    }

    void
    updateHistories(ThreadID tid, Addr pc, bool uncond, bool taken,
                    Addr target, const StaticInstPtr &inst,
                    void *&bp_history) override
    {
        // Placeholder
    }

    void update(ThreadID tid, Addr pc, bool taken, void *&bp_history,
                bool squashed, const StaticInstPtr &inst,
                Addr target) override;

    void
    squash(ThreadID tid, void *&bp_history) override
    {
        assert(bp_history == NULL);
    }

  private:
    /** static prediction taken **/
    const bool staticPredictionAlwaysTaken;
};

class StaticIndirectBP : public IndirectPredictor
{
  public:
    StaticIndirectBP(const StaticIndirectBPParams &params);

    /** Indirect predictor interface */
    void
    reset() override
    {}

    const PCStateBase *
    lookup(ThreadID tid, InstSeqNum sn, Addr pc, void *&iHistory) override
    {
        return nullptr;
    }
    void
    update(ThreadID tid, InstSeqNum sn, Addr pc, bool squash, bool taken,
           const PCStateBase &target, BranchType br_type,
           void *&iHistory) override
    {}
    void
    squash(ThreadID tid, InstSeqNum sn, void *&iHistory) override
    {}
    void
    commit(ThreadID tid, InstSeqNum sn, void *&iHistory) override
    {}
};

} // namespace branch_prediction
} // namespace gem5

#endif // __CPU_PRED_STATIC_PRED_HH__
