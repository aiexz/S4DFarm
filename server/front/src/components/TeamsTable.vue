<template>
  <q-table
    virtual-scroll
    dense
    :rows="enrichedTeams"
    :columns="columns"
    :rows-per-page-options="[0]"
    style="height: 80vh"
    row-key="name"
    no-data-label="No teams to attack"
    table-header-class="bg-cbs text-cbs"
  >
    <template v-slot:no-data="{ message }">
      <div class="full-width row flex-center text-accent q-gutter-sm">
        <q-icon size="2em" name="sentiment_dissatisfied" />
        <span> Well this is sad... {{ message }} </span>
      </div>
    </template>
    <template v-slot:header-cell="props">
      <q-th :props="props" :style="{ textAlign: 'center' }">
        {{ props.col.label }}
      </q-th>
    </template>
    <template v-slot:body-cell-address="props">
      <q-td :props="props">
        <div>
          {{ props.value }}
          <q-btn
            size="sm"
            flat
            round
            icon="content_copy"
            @click="copyToClipboard(props.value)"
          />
        </div>
      </q-td>
    </template>
    <template v-slot:body-cell-status="props">
      <q-td :props="props">
        <q-badge
          v-if="props.value === 'unhit'"
          color="negative"
          label="UNHIT"
        />
        <q-badge
          v-else-if="props.value === 'ok'"
          color="positive"
          label="ACTIVE"
        />
        <q-badge v-else color="warning" label="FAILING" />
      </q-td>
    </template>
    <template v-slot:body-cell-success_rate="props">
      <q-td :props="props">
        <span>{{ props.value }}%</span>
      </q-td>
    </template>
  </q-table>
</template>

<script>
import { mapState } from "vuex";
import { copyToClipboard } from "quasar";
import moment from "moment";

export default {
  data: function () {
    return {
      columns: [
        { name: "name", label: "Name", field: "name", align: "left" },
        {
          name: "address",
          label: "Address",
          field: "address",
          align: "center",
        },
        { name: "status", label: "Status", field: "status", align: "center" },
        { name: "total_runs", label: "Runs", field: "total_runs", align: "center" },
        { name: "success_rate", label: "Success %", field: "success_rate", align: "center" },
        { name: "flags_found", label: "Flags Found", field: "flags_found", align: "center" },
        { name: "last_run", label: "Last Hit", field: "last_run", align: "center" },
      ],
    };
  },
  computed: {
    ...mapState(["teams", "telemetry"]),
    enrichedTeams() {
      const statsMap = {};
      if (this.telemetry?.teams) {
        for (const t of this.telemetry.teams) {
          statsMap[t.team] = t;
        }
      }
      return this.teams.map((team) => {
        const stats = statsMap[team.name] || {};
        return {
          ...team,
          status: stats.status || "unhit",
          total_runs: stats.total_runs || 0,
          success_rate: stats.success_rate != null ? stats.success_rate : 0,
          flags_found: stats.flags_found || 0,
          last_run: stats.last_run
            ? moment.unix(stats.last_run).format("HH:mm:ss")
            : "Never",
        };
      });
    },
  },
  methods: { copyToClipboard },
};
</script>

<style></style>
