import re
import os
import sqlite3
import logging

class CausalityAgent:
    def __init__(self, path):
        self.corr_ind = 0
        self.causality_ind = 0

        db_file = os.path.join(path, 'pnnl-dataset.db')
        if os.path.isfile(db_file):
            self.cadb = sqlite3.connect(db_file)
        else:
            # create table if it doesn't exist
            fp = open(db_file, 'w')
            fp.close()
            self.cadb = sqlite3.connect(db_file)
            self.populate_tables(path)

    def __del__(self):
        self.cadb.close()

    def populate_tables(self, path):
        self.populate_correlation_table(path)
        self.populate_causality_table(path)
        self.populate_mutsig_table(path)
        self.populate_unexplained_table()
        self.populate_explained_table()
        self.populate_sif_relations_table(path)
        self.populate_mutex_table(path)


    def populate_causality_table(self, path):
        opposite_rel = {
            'phosphorylates': 'is-phosphorylated-by',
            'dephosphorylates': 'is-dephosphorylated-by',
            'upregulates-expression': 'expression-is-upregulated-by',
            'downregulates-expression': 'expression-is-downregulated-by',
        }

        causality_path = os.path.join(path, 'causative-data-centric.sif')
        causality_file = open(causality_path, 'r')

        with self.cadb:
            cur = self.cadb.cursor()
            try:
                cur.execute(
                    "CREATE TABLE Causality(Id1 TEXT, PSite1 TEXT, Id2 TEXT, PSite2 TEXT, Rel TEXT, UriStr TEXT)")
            except:
                pass

            for line in causality_file:
                vals = line.split('\t')
                vals[len(vals) - 1] = vals[len(vals) - 1].rstrip('\n')
                id_str1 = vals[0].upper().split('-')
                id1 = id_str1[0]
                if len(id_str1) > 1:
                    p_site1 = id_str1[1]
                else:
                    p_site1 = ' '

                id_str2 = vals[2].upper().split('-')
                id2 = id_str2[0]

                if len(id_str2) > 1:
                    p_site2 = id_str2[1]
                else:
                    p_site2 = ' '

                rel = vals[1]

                uri_arr = []
                if vals[3]:
                    uri_arr = vals[3].split(" ")

                if len(uri_arr) == 0:
                    uri_arr = [vals[3]]

                uri_str = ""
                for uri in uri_arr:
                    uri_str = uri_str + "uri= " + uri + "&"

                opp_rel = opposite_rel[rel]
                cur.execute("INSERT INTO Causality VALUES(?, ?, ?, ?, ?, ?)", (id1, p_site1, id2, p_site2, rel, uri_str))
                # opposite relation
                cur.execute("INSERT INTO Causality VALUES(?, ?, ?, ?, ?, ?)", (id2, p_site2, id1, p_site1, opp_rel, uri_str))

        causality_file.close()

    def populate_correlation_table(self, path):
        pnnl_path = os.path.join(path, 'PNNL-ovarian-correlations.txt')
        pnnl_file = open(pnnl_path, 'r')

        with self.cadb:
            cur = self.cadb.cursor()
            try:
                cur.execute(
                    "CREATE TABLE Correlations(Id1 TEXT, PSite1 TEXT, Id2 TEXT, PSite2 TEXT, Corr REAL, PVal REAL)")
            except:
                pass

            for line in pnnl_file:
                if line.find('/') > -1:  # incorrectly formatted strings
                    continue
                vals = line.split('\t')
                vals[len(vals) - 1] = vals[len(vals) - 1].rstrip('\n')
                id_str1 = vals[0].upper().split('-')
                id1 = id_str1[0]
                if len(id_str1) > 1:
                    p_site1 = id_str1[1]
                else:
                    p_site1 = ' '

                id_str2 = vals[1].upper().split('-')
                id2 = id_str2[0]

                if len(id_str2) > 1:
                    p_site2 = id_str2[1]
                else:
                    p_site2 = ' '

                corr = float(vals[2])

                p_val = float(vals[3])

                cur.execute("INSERT INTO Correlations VALUES(?, ?, ?, ?, ?, ?)", (id1, p_site1, id2, p_site2, corr, p_val))

        pnnl_file.close()

    def populate_mutsig_table(self, path):
        mutsig_path = os.path.join(path, 'scores-mutsig.txt')
        mutsig_file = open(mutsig_path, 'r')

        with self.cadb:
            cur = self.cadb.cursor()
            cur.execute("DROP TABLE IF EXISTS MutSig")
            try:
                cur.execute("CREATE TABLE MutSig(Id TEXT,  PVal REAL)")
            except:
                pass

            for line in mutsig_file:
                vals = line.split('\t')
                gene_id = vals[1]
                p_val = vals[17]
                cur.execute("INSERT INTO MutSig VALUES(?, ?)", (gene_id,  p_val))

        mutsig_file.close()

    # Find the correlations with a causal explanation
    def populate_explained_table(self):
        with self.cadb:
            cur = self.cadb.cursor()
            cur.execute("DROP TABLE IF EXISTS Explained_Correlations")
            cur.execute("CREATE TABLE Explained_Correlations AS SELECT * FROM Correlations "
                        "LEFT JOIN Causality ON Causality.Id1 = Correlations.Id1 AND Causality.Id2 = Correlations.Id2  "
                        "AND Causality.PSite1 = Correlations.PSite1 AND Causality.PSite2 = Correlations.PSite2 "
                        "WHERE Rel IS NOT NULL",
                        ).fetchall()

    # Find the correlations without a causal explanation
    def populate_unexplained_table(self):
        with self.cadb:
            cur = self.cadb.cursor()
            cur.execute("DROP TABLE IF EXISTS Unexplained_Correlations")
            cur.execute("CREATE TABLE Unexplained_Correlations AS SELECT * FROM Correlations "
                        "LEFT JOIN Causality ON Causality.Id1 = Correlations.Id1 AND Causality.Id2 = Correlations.Id2  "
                        "AND Causality.PSite1 = Correlations.PSite1 AND Causality.PSite2 = Correlations.PSite2 "
                        "WHERE Rel IS NULL",
                        ).fetchall()

    #All sif relations from PathwayCommons
    def populate_sif_relations_table(self, path):
        pc_path = os.path.join(path, 'PC.sif')
        pc_file = open(pc_path, 'r')

        with self.cadb:
            cur = self.cadb.cursor()
            cur.execute("DROP TABLE IF EXISTS Sif_Relations")
            cur.execute("CREATE TABLE Sif_Relations(Id1 TEXT,  Id2 TEXT, Rel TEXT)")
            for line in pc_file:
                vals = line.split('\t')
                vals[len(vals) - 1] = vals[len(vals) - 1].rstrip('\n')
                id1 = vals[0].upper()
                id2 = vals[2].upper()
                rel = vals[1]
                cur.execute("INSERT INTO Sif_Relations VALUES(?, ?, ?)", (id1, id2, rel))

        pc_file.close()

    def populate_mutex_table(self, path):
        mutex_path = os.path.join(path, 'ranked-groups.txt')
        mutex_file = open(mutex_path, 'r')

        with self.cadb:
            cur = self.cadb.cursor()
            cur.execute("DROP TABLE IF EXISTS Mutex")
            try:
                cur.execute("CREATE TABLE Mutex(Id1 TEXT, Id2 TEXT, Id3 TEXT, Score REAL)")
            except:
                pass

            for line in mutex_file:
                vals = line.split('\t')
                vals[len(vals) - 1] = vals[len(vals) - 1].rstrip('\n')
                score = vals[0]
                gene1 = vals[2]
                gene2 = vals[3]
                if len(vals) > 4:
                    gene3 = vals[4]
                else:
                    gene3 = None

                cur.execute("INSERT INTO Mutex VALUES(?, ?, ?, ?)", (gene1, gene2, gene3, score))

        mutex_file.close()

    @staticmethod
    def row_to_causality(row):
        """
        :param row: Row from sql table
        :return:  Causality object
        Positions need to be trimmed to correct PC formatting. E.g. s100S for pSite
        """
        sites1 = re.findall('([TYS][0-9]+)[TYS]', row[1])
        sites2 = re.findall('([TYS][0-9]+)[TYS]', row[3])
        res1 = [site[0] for site in sites1]
        res2 = [site[0] for site in sites2]
        pos1 = [site[1:] for site in sites1]
        pos2 = [site[1:] for site in sites2]
        mods1 = [{'mod_type': 'phosphorylation',
                  'residue': site[0],
                  'position': site[1:],
                  'is_modified': True}
                  for site in sites1]
        mods2 = [{'mod_type': 'phosphorylation',
                  'residue': site[0],
                  'position': site[1:],
                  'is_modified': True}
                  for site in sites2]
        causality = {'id1': row[0], 'mods1': mods1,
                     'id2': row[2], 'mods2': mods2,
                     'rel': row[4]}
        return causality

    # Convert the row from sql table into correlation object
    # Positions need to be trimmed to correct PC formatting. E.g. s100S for pSite
    @staticmethod
    def row_to_correlation(row):
        """
        :param row: Row from sql table
        :return:  Correlation object
        Positions need to be trimmed to correct PC formatting. E.g. s100S for pSite
        """
        l1 = len(row[1])
        p_site1 = row[1][1:l1-1]

        l2 = len(row[3])
        p_site2 = row[3][1:l2-1]

        corr = {'id1': row[0], 'pSite1': p_site1,
                'id2': row[2], 'pSite2': p_site2, 'correlation': row[4],
                'pVal': row[5],
                'explainable': "\"unassigned\""}
        return corr

    def find_causality(self, param):
        """Find the causal relationship between gene1 and gene2"""
        with self.cadb:
            cur = self.cadb.cursor()
            source = param.get('source').get('id')
            target = param.get('target').get('id')

            rows = cur.execute("SELECT * FROM Causality WHERE Id1 = ? AND  Id2 = ?",
                               (source, target)).fetchall()
            if len(rows) > 0:
                row = rows[0]
                causality = self.row_to_causality(row)
                return causality

            else:
                return ''

    def find_causality_targets(self, param):
        """Find the causal relationship from param.source to target"""
        with self.cadb:
            cur = self.cadb.cursor()
            print(param)
            id = param.get('id')
            p_site = param.get('pSite')
            rel = param.get('rel')

            if rel.upper() == "MODULATES":
                rows = cur.execute("SELECT * FROM Causality WHERE Id1 = ?", (id,)).fetchall()
            else:
                rows = cur.execute("SELECT * FROM Causality WHERE Id1 = ? AND Rel = ?", (id, rel)).fetchall()

            targets = []
            for row in rows:
                causality = self.row_to_causality(row)
                targets.append(causality)

            return targets

    def find_next_correlation(self, gene):
        """Returns the next interesting relationship, which can be explained or unexplained"""

        with self.cadb:
            cur = self.cadb.cursor()

            causal_rows = cur.execute("SELECT * FROM Explained_Correlations WHERE Id1 = ? OR Id2 = ? "
                                      "ORDER BY ABS(Corr) DESC",
                                      (gene, gene)).fetchall()

            row_cnt = len(causal_rows)
            if row_cnt > self.causality_ind:
                row = causal_rows[self.causality_ind]
                self.causality_ind = self.causality_ind + 1

                corr = self.get_correlation_between(row[0], row[1], row[2], row[3])
                corr['explainable'] = "\"explainable\""
            else:
                corr = self.find_next_unexplained_correlation(gene)

            # revert correlation info
            if corr != '' and corr['id2'] == gene:
                tmp = corr['id1']
                corr['id1'] = corr['id2']
                corr['id2'] = tmp
                tmp = corr['pSite1']
                corr['pSite1'] = corr['pSite2']
                corr['pSite2'] = tmp

            return corr

    def get_correlation_between(self, gene1, p_site1, gene2, p_site2):
        """We know that there's a correlation between these elements"""
        with self.cadb:
            cur = self.cadb.cursor()
            # Don't change the order
            rows = cur.execute("SELECT * FROM Correlations WHERE Id1 = ? AND PSite1 = ?  AND Id2 = ?  AND PSite2 = ? "
                               "OR Id1 = ? AND PSite1 = ?  AND Id2 = ?  AND PSite2 = ? ",
                               (gene1, p_site1, gene2, p_site2, gene2, p_site2, gene1, p_site1)).fetchall()

            corr = ''
            if len(rows) > 0:
                row = rows[0]
                corr = self.row_to_correlation(row)

            return corr

    def find_next_unexplained_correlation(self, gene):
        """Find the next highest unexplained correlation"""
        with self.cadb:
            cur = self.cadb.cursor()
            rows = cur.execute("SELECT * FROM Unexplained_Correlations "
                               "WHERE Id1 = ? OR Id2 = ? ORDER BY ABS(Corr) DESC",
                               (gene, gene)).fetchall()

            row_cnt = len(rows)
            if row_cnt > self.corr_ind:
                row = rows[self.corr_ind]
                self.corr_ind = self.corr_ind + 1
                corr = self.row_to_correlation(row)
                corr['explainable'] = "\"unexplainable\""
                return corr
            else:
                return ''

    def find_mut_sig(self, gene):
        """Find mutation significance"""
        with self.cadb:
            cur = self.cadb.cursor()
            p_val = cur.execute("SELECT PVal FROM MutSig WHERE Id = ?", (gene,)).fetchone()

            if p_val[0] < 0.01:
                return "highly significant"
            elif p_val[0] < 0.05:
                return "significant"
            else:
                return "not significant"

    def find_common_upstreams(self, genes):
        """Find common upstreams between gene1 and gene2"""
        with self.cadb:
            cur = self.cadb.cursor()

            if len(genes) < 2:
                return ''

            gene1 = genes[0]
            gene2 = genes[1]

            upstreams = cur.execute("SELECT s1.Id1 FROM Sif_Relations s1 "
                                    "INNER JOIN Sif_Relations s2 ON (s2.Id1 = s1.Id1 AND s1.Id2 = ? AND s2.id2 = ? AND  "
                                    "s1.Rel = 'controls-state-change-of' AND s2.Rel = s1.Rel)",
                                    (gene1, gene2)).fetchall()

            for i in range(2, len(genes)):
                gene = genes[i]
                upstream_arr = []
                for upstream in upstreams:
                    upstream_arr.append(upstream[0])

                query = "SELECT Id1 FROM Sif_Relations WHERE Rel = 'controls-state-change-of' AND Id2 = ? AND Id1 IN (" \
                        + ", ".join((("'"+str(upstream)+"'") for upstream in upstream_arr)) + ")"

                upstreams = cur.execute(query, (gene,)).fetchall()


            # format upstreams
            upstream_list = []
            for genes in upstreams:
                upstream_list.append({'name': genes[0]})

            return upstream_list

    def find_mutex(self, gene):
        """Find a mutually exclusive group that includes gene"""

        with self.cadb:
            cur = self.cadb.cursor()
            groups = cur.execute("SELECT * FROM Mutex WHERE Id1 = ? OR Id2 = ? OR Id3 = ?",
                                 (gene, gene, gene)).fetchall()

        # format groups
        mutex_list = []
        for group in groups:
            mutex = {'group': [], 'score': group[len(group) - 1]}
            for i in range(len(group) - 1):
                mutex['group'].append(group[i])
            mutex_list.append(mutex)

        return mutex_list


#test
def print_result(res):
    print(res)

# ca = CausalityAgent('./resources')
# ca.populate_mutex_table('./resources')

# print(ca.find_mutex('PIK3CA'))


# ca.find_causality_targets({'id':'MAPK1', 'rel': 'phosphorylates'}, print_result)
# ca.find_causality_targets({'id':'BRAF', 'rel': 'is-phosphorylated-by'}, print_result)
#
# ca.populate_mutsig_table()
# ca.populate_sif_relations_table()

# ca.populate_explained_table()
# print(ca.find_next_unexplained_correlation('AKT1'))
# ca.find_next_unexplained_correlation('AKT1', print_result)
# ca.find_next_unexplained_correlation('AKT1', print_result)
# # ca.find_causality_targets({'source':{'id' :'BRAF', 'pSite' :'S365S', 'rel': 'is-phosphorylated-by'}},print_result)
# ca.find_next_correlation('AKT1',print_result)
# ca.find_next_correlation('AKT1',print_result)
# ca.find_next_correlation('AKT1',print_result)
# ca.find_next_correlation('AKT1',print_result)
# ca.find_next_correlation('AKT1',print_result)
# # ca.find_next_correlation('AKT1',print_result)
# ca.find_correlation_between('AKT1', 'BRAF')
# ca.find_all_correlations('AKT1')
# print(ca.find_mut_sig('TP53'))
# ca.find_common_upstreams('RAC1', 'RAC2')
# ca.find_common_upstreams(['AKT1', 'BRAF', 'MAPK1'], print_result)
