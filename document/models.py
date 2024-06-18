import logging
import re
import uuid

from citeproc import CitationStylesStyle, CitationStylesBibliography, formatter, Citation, CitationItem
from citeproc.source.json import CiteProcJSON
from django.db import models
from django.utils.translation import gettext_lazy as _
# from pybtex.database import BibliographyData, Entry

from core.utils.statics import EN_FIRST_NAMES

logger = logging.getLogger(__name__)

PUB_TYPE_2_CSL_TYPE = {
    "Review": "review",
    "JournalArticle": "article-journal",
    "CaseReport": "document",
    "ClinicalTrial": "report",
    "Dataset": "dataset",
    "Editorial": "article-journal",
    "LettersAndComments": "post",
    "MetaAnalysis": "article-journal",
    "News": "article-newspaper",
    "Study": "article-journal",
    "Book": "book",
    "BookSection": "chapter"
}

class Document(models.Model):
    class TypeChoices(models.TextChoices):
        PERSONAL = 'personal', _('personal')
        PUBLIC = 'public', _('public')

    class StateChoices(models.TextChoices):
        # UPLOADING = 'uploading', _('uploading')
        UNDONE = 'undone', _('undone')
        PARSING = 'in_progress', _('in_progress')
        COMPLETED = 'completed', _('completed')
        FAILED = 'error', _('error')

    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    doc_id = models.BigIntegerField(null=True)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    collection_type = models.CharField(
        null=True, blank=True, max_length=32, default=TypeChoices.PERSONAL, db_default=TypeChoices.PERSONAL)
    collection = models.ForeignKey(
        'collection.Collection', db_constraint=False, on_delete=models.DO_NOTHING, null=True,
        db_column='collection_id')
    title = models.CharField(null=True, blank=True, db_index=True, max_length=512, default=None, db_default=None)
    abstract = models.TextField(null=True, blank=True, db_default=None)
    authors = models.JSONField(null=True)
    doi = models.CharField(null=True, blank=True, max_length=256, default=None, db_default=None)
    categories = models.JSONField(null=True)
    pages = models.IntegerField(null=True)
    year = models.IntegerField(null=True)
    pub_date = models.DateField(null=True)
    pub_type = models.CharField(null=True, blank=True, max_length=32, default=None, db_default=None)
    venue = models.CharField(null=True, blank=True, max_length=256, default=None, db_default=None)
    journal = models.CharField(null=True, blank=True, max_length=256, default=None, db_default=None)
    conference = models.CharField(null=True, blank=True, max_length=256, default=None, db_default=None)
    keywords = models.JSONField(null=True)
    full_text_accessible = models.BooleanField(null=True, default=None, db_default=None)
    citation_count = models.IntegerField(null=True)
    reference_count = models.IntegerField(null=True)
    citations = models.JSONField(null=True)
    references = models.JSONField(null=True)
    state = models.CharField(
        null=True, blank=True, max_length=32, default=StateChoices.UNDONE, db_default=StateChoices.UNDONE)
    object_path = models.CharField(null=True, blank=True, max_length=256)
    source_url = models.CharField(null=True, blank=True, max_length=256)
    checksum = models.CharField(null=True, blank=True, db_index=True, max_length=64)
    ref_collection_id = models.CharField(null=True, blank=True, db_index=True, max_length=36)
    ref_doc_id = models.BigIntegerField(null=True)
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    @staticmethod
    def raw_by_docs(docs, fileds='*', where=None):
        if fileds != '*' and isinstance(fileds, list):
            fileds = ','.join(fileds)
        doc_ids_str = ','.join([f"('{d['collection_id']}', {d['doc_id']})" for d in docs])
        sql = f"SELECT {fileds} FROM document WHERE (collection_id, doc_id) IN ({doc_ids_str})"
        if where:
            sql += f"and {where}"
        return Document.objects.raw(sql)

    @staticmethod
    def difference_docs(docs1, docs2):
        docs1_dict = {f"{d['collection_id']}-{d['doc_id']}": d for d in docs1}
        docs2_dict = {f"{d['collection_id']}-{d['doc_id']}": d for d in docs2}
        diff_docs = []
        for k, v in docs1_dict.items():
            if k not in docs2_dict:
                diff_docs.append(v)
        return diff_docs

    @staticmethod
    def get_doc_apa(authors, year, title, venue):
        """
        https://wordvice.cn/apa-citation-generator
        author:  （姓，名首字母）  fistname lastname
        authors. (pub_date). title. venue
        1. authors:
            1. Initials are separated and ended by a period eg Mitchell, J.A
            2. Multiple authors are separated by commas and an ampersand eg Mitchell, J.A., Thomson, M., & Coyne, R
            3. Multiple authors with the same sumame and initial: add their name in square brackets eg Mendeley, J. [James].
        2. pub_date
            有 pub_date 直接使用 (pub_date) 展示，没有 date，显示未 (n.d)
        3. 无作者、无 title、无 venue 的情况直接显示空
        :param authors:
        :param title:
        :param venue:
        :param year:
        :return:
        """

        def format_authors(authors: list):
            def is_english(string):
                pattern = "^[A-Za-z -.áàâèéêëîïôöùûüçÀÂÈÉÊËÎÏÔÖÙÛÜÇØ]+$"
                if re.match(pattern, string):
                    return True
                else:
                    return False

            formatted_authors = []
            for author in authors:
                author = author.strip()
                is_en = is_english(author)
                if is_en:
                    sub_chars = author.split(' ')
                    last_sub_chars = [s.strip('.-') for s in sub_chars[:-1]]
                    if (
                        len(sub_chars) == 2 and len(sub_chars[0]) > 1
                        and sub_chars[0].strip('.').lower() in (EN_FIRST_NAMES['1'] + EN_FIRST_NAMES['2'])
                        and sub_chars[1].strip('.').lower() not in (EN_FIRST_NAMES['1'] + EN_FIRST_NAMES['2'])
                    ):
                        if sub_chars[1].find('-') != -1:
                            sub_chars = [sub_chars[0]] + sub_chars[1].split('-')
                        last_sub_chars_format = ''.join(
                            [s[0] + '.' if s.find('.') == -1 else s for s in sub_chars[1:]])
                        f_author = f"{sub_chars[0]}, {last_sub_chars_format}"
                    else:
                        if sub_chars[0].find('-') != -1:
                            sub_chars = sub_chars[0].split('-') + sub_chars[1:]
                            last_sub_chars = [s.strip('.-') for s in sub_chars[:-1]]
                        last_sub_chars_format = ''.join(
                            [s[0].upper() + '.' if s.find('.') == -1 else s for s in last_sub_chars])
                        f_author = f"{sub_chars[-1]}, {last_sub_chars_format}"
                else:
                    f_author = author
                # print(f"{is_english(author)}({author})--({f_author})")
                formatted_authors.append(f_author)
            ret_authors = None
            if formatted_authors and len(formatted_authors) == 1:
                ret_authors = formatted_authors[0]
            elif formatted_authors and len(formatted_authors) == 2:
                ret_authors = f"{formatted_authors[0]} & {formatted_authors[1]}"
            elif formatted_authors and len(formatted_authors) < 6:
                ret_authors = ', '.join(formatted_authors[:-1]) + f", & {formatted_authors[-1]}"
            elif formatted_authors:
                ret_authors = formatted_authors[0] + f" et al."
            return ret_authors

        if not year:
            year = 'n.d'
        if title:
            title = title.strip('.')
            if venue:
                title += '.'
                venue = f"<em>{venue}</em>"
        return f"{format_authors(authors)} ({year}). {title} {venue}"

    @staticmethod
    def get_doc_mla(authors, year, title, venue):
        """
        https://wordvice.cn/citation-guide/mla
            作者姓氏, 作者名字 中间名字. “网页标题.” 网站名称, 出版社名称, 出版日期, URL.
        :param authors:
        :param year:
        :param title:
        :param venue:
        :return:
        """

        def format_authors(authors: list):
            def is_english(string):
                pattern = "^[A-Za-z -.áàâèéêëîïôöùûüçÀÂÈÉÊËÎÏÔÖÙÛÜÇØ]+$"
                if re.match(pattern, string):
                    return True
                else:
                    return False

            formatted_authors = []
            for author in authors:
                author = author.strip()
                is_en = is_english(author)
                if is_en:
                    sub_chars = author.split(' ')
                    last_sub_chars = [s for s in sub_chars[:-1]]
                    if (
                        len(sub_chars) == 2 and len(sub_chars[0]) > 1
                        and sub_chars[0].strip('.').lower() in (EN_FIRST_NAMES['1'] + EN_FIRST_NAMES['2'])
                        and sub_chars[1].strip('.').lower() not in (EN_FIRST_NAMES['1'] + EN_FIRST_NAMES['2'])
                    ):
                        if sub_chars[1].find('-') != -1:
                            sub_chars = [sub_chars[0]] + sub_chars[1].split('-')
                        last_sub_chars_format = ' '.join([s for s in sub_chars[1:]])
                        f_author = f"{sub_chars[0]} {last_sub_chars_format}"
                    else:
                        if sub_chars[0].find('-') != -1:
                            sub_chars = sub_chars[0].split('-') + sub_chars[1:]
                            last_sub_chars = [s for s in sub_chars[:-1]]
                        last_sub_chars_format = ''.join([s for s in last_sub_chars])
                        f_author = f"{sub_chars[-1]} {last_sub_chars_format}"
                else:
                    f_author = author
                # print(f"{is_english(author)}({author})--({f_author})")
                formatted_authors.append(f_author)
            ret_authors = ''
            if formatted_authors and len(formatted_authors) == 1:
                ret_authors = formatted_authors[0]
            elif formatted_authors and len(formatted_authors) == 2:
                ret_authors = f"{formatted_authors[0]} & {formatted_authors[1]}"
            elif formatted_authors and len(formatted_authors) < 6:
                ret_authors = ', '.join(formatted_authors[:-1]) + f", & {formatted_authors[-1]}"
            elif formatted_authors:
                ret_authors = formatted_authors[0] + f" et al."
            return ret_authors

        if not year:
            year = 'n.d'
        if title:
            title = title.strip('.')
            if venue:
                title += '.'
                venue = f"<em>{venue}</em>"
        authors_str = format_authors(authors).strip('.')
        authors_str = f"{authors_str}." if authors_str else ''
        return f"{authors_str} \"{title}\" {venue}, Accessed {year}.  "

    @staticmethod
    def get_doc_gbt(authors, year, title, venue, pub_type_tag):
        def format_authors(authors: list):
            def is_english(string):
                pattern = "^[A-Za-z -.áàâèéêëîïôöùûüçÀÂÈÉÊËÎÏÔÖÙÛÜÇØ]+$"
                if re.match(pattern, string):
                    return True
                else:
                    return False

            formatted_authors = []
            for author in authors:
                author = author.strip()
                is_en = is_english(author)
                if is_en:
                    sub_chars = author.split(' ')
                    last_sub_chars = [s.strip('.-') for s in sub_chars[:-1]]
                    if (
                        len(sub_chars) == 2 and len(sub_chars[0]) > 1
                        and sub_chars[0].strip('.').lower() in (EN_FIRST_NAMES['1'] + EN_FIRST_NAMES['2'])
                        and sub_chars[1].strip('.').lower() not in (EN_FIRST_NAMES['1'] + EN_FIRST_NAMES['2'])
                    ):
                        if sub_chars[1].find('-') != -1:
                            sub_chars = [sub_chars[0]] + sub_chars[1].split('-')
                        last_sub_chars_format = ''.join(
                            [s[0] + '.' if s.find('.') == -1 else s for s in sub_chars[1:]])
                        f_author = f"{sub_chars[0]} {last_sub_chars_format}"
                    else:
                        if sub_chars[0].find('-') != -1:
                            sub_chars = sub_chars[0].split('-') + sub_chars[1:]
                            last_sub_chars = [s.strip('.-') for s in sub_chars[:-1]]
                        last_sub_chars_format = ''.join(
                            [s[0].upper() + '.' if s.find('.') == -1 else s for s in last_sub_chars])
                        f_author = f"{sub_chars[-1]} {last_sub_chars_format}"
                else:
                    f_author = author
                # print(f"{is_english(author)}({author})--({f_author})")
                formatted_authors.append(f_author)
            ret_authors = ''
            if formatted_authors and len(formatted_authors) <= 3:
                ret_authors = ', '.join(formatted_authors)
            elif formatted_authors and len(formatted_authors) == 2:
                ret_authors = f"{formatted_authors[0]} & {formatted_authors[1]}"
            elif formatted_authors and len(formatted_authors) < 6:
                ret_authors = ', '.join(formatted_authors[:-1]) + f", & {formatted_authors[-1]}"
            elif formatted_authors:
                ret_authors = formatted_authors[0] + f" et al."
            return ret_authors

        if not year:
            year = 'n.d'
        if title:
            title = title.strip('.')
            if venue:
                venue = f"<em>{venue}</em>,"
        return f"{format_authors(authors)} {title}{pub_type_tag}. {venue} {year}."

    def get_csl_formate(self, style):
        title = self.title
        year = self.year
        venue = self.venue if self.venue else self.journal if self.journal else self.conference \
            if self.conference else self.venue
        pub_type = self.pub_type

        def format_authors(authors: list):
            final_authors = []
            for author in authors:
                author_split = author.split(' ')
                last_name = author_split[-1].strip()
                first_name = author_split[0].strip()
                family = last_name
                given = ' '.join(author_split[:-1])

                if (
                    first_name.lower() in (EN_FIRST_NAMES['1'] + EN_FIRST_NAMES['2'])
                    and last_name.lower() not in (EN_FIRST_NAMES['1'] + EN_FIRST_NAMES['2'])
                ):
                    family = first_name
                    given = ' '.join(author_split[1:])
                final_authors.append({
                    'family': family,
                    'given': given,
                })
            return final_authors

        style_csl_map = {
            'apa': 'document/csl/apa.csl',
            'mla': 'document/csl/modern-language-association.csl',
            'gbt': 'document/csl/china-national-standard-gb-t-7714-2015-numeric.csl',
            'bibtex': 'document/csl/bibtex.csl',
        }
        if style not in style_csl_map:
            return None
        if not PUB_TYPE_2_CSL_TYPE.get(pub_type) and style == 'gbt':
            style_csl_map['gbt'] = 'document/csl/china-national-standard-gb-t-7714-2015-numeric-no-type-code.csl'
        paper_type = PUB_TYPE_2_CSL_TYPE[pub_type] if PUB_TYPE_2_CSL_TYPE.get(pub_type) else 'article-journal'
        json_id = str(uuid.uuid4())
        json_data = [{
            'id': json_id,
            'author': format_authors(self.authors),
            'title': title,
            "issued": {"date-parts": [[year]]},
            # 'publisher': venue,
            'container-title': venue,
            "references": '',  # apa
            'type': paper_type,
        }]
        try:
            bib_source = CiteProcJSON(json_data)
            # for key, entry in bib_source.items():
            #    print(key)
            #    for name, value in entry.items():
            #        print('   {}: {}'.format(name, value))

            bib_style = CitationStylesStyle(style_csl_map[style], validate=False)
            bibliography = CitationStylesBibliography(bib_style, bib_source, formatter.html)

            citation1 = Citation([CitationItem(json_id)])
            bibliography.register(citation1)
            formatted_text = str(bibliography.bibliography()[0])
            if style == 'gbt':
                formatted_text = formatted_text[3:]
            elif style == 'mla':
                formatted_text = formatted_text.replace('“', '"').replace('”', '"')

        except Exception as e:
            logger.warning('Error when formatting the document. ' + str(e))
            formatted_text = ''
        return formatted_text

    def get_bibtex_format(self):
        title = self.title
        year = self.year
        venue = self.venue if self.venue else self.journal if self.journal else self.conference \
            if self.conference else self.venue
        pub_type = self.pub_type
        if not PUB_TYPE_2_CSL_TYPE.get(pub_type):
            paper_type = 'article-journal'
        else:
            paper_type = PUB_TYPE_2_CSL_TYPE[pub_type]
        paper_type_2_bibtex_type = {
            "book":"book",
            "report":"techreport",
            "article":"article",
            "article-journal":"article",
            "article-newspaper":"article",
            "paper-conference":"inproceedings",
            "chapter":"inbook",
            "dataset":"misc",
            "document":"misc",
            "review":"misc",
            "post":"misc",
        }
        bibtex_type = paper_type_2_bibtex_type[paper_type]
        if self.authors:
            author_split = self.authors[0].split(' ')
            first_name = author_split[0].strip().strip('.')
            last_name = author_split[-1].strip().strip('.')
            if (
                first_name.lower() in (EN_FIRST_NAMES['1'] + EN_FIRST_NAMES['2'])
                and last_name.lower() not in (EN_FIRST_NAMES['1'] + EN_FIRST_NAMES['2'])
            ):
                family_name = first_name
            else:
                family_name = last_name
        else:
            family_name = 'author'
        title_split = title.split(' ')
        rest_title = [t[0].upper() for t in title_split[1:]]
        title_key = f"{title_split[0]}{''.join(rest_title[:2])}"
        bib_key = f"{family_name}{year}{title_key}"
        template1 = '''@{bibtex_type}{{{bib_key},
    author={{{authors}}},
    title={{{title}}},
    journal={{{venue}}},
    year={{{year}}}
}}'''
        template2 = '''@{bibtex_type}{{{bib_key},
    author={{{authors}}},
    title={{{title}}},
    year={{{year}}}
}}'''
        if venue:
            bibtex_str = template1.format(
                bib_key=bib_key,
                bibtex_type=bibtex_type,
                authors=' and '.join(self.authors),
                title=title,
                venue=venue,
                year=year,
            )
        else:
            bibtex_str = template2.format(
                bib_key=bib_key,
                bibtex_type=bibtex_type,
                authors=' and '.join(self.authors),
                title=title,
                year=year,
            )
        # bib_data = BibliographyData({
        #     f"{bib_key}": Entry(bibtex_type, [
        #         ('author', ' and '.join(self.authors)),
        #         ('title', title),
        #         ('journal', venue),
        #         ('year', str(year)),
        #     ]),
        # })
        # try:
        #     bibtex_str = bib_data.to_string('bibtex')
        # except Exception as e:
        #     logger.warning('Error when bibtex_format the document. ' + str(e))
        #     bibtex_str = ''
        return bibtex_str

    class Meta:
        unique_together = ['collection', 'doc_id']
        db_table = 'document'
        verbose_name = 'document'


class DocumentLibrary(models.Model):
    class TaskStatusChoices(models.TextChoices):
        PENDING = 'pending', _('pending')
        QUEUEING = 'queueing', _('queueing')
        IN_PROGRESS = 'in_progress', _('in_progress')
        COMPLETED = 'completed', _('completed')
        TO_BE_CANCELLED = 'to_be_cancelled', _('to_be_cancelled')
        CANCELLED = 'cancelled', _('cancelled')
        ERROR = 'error', _('error')
        # CANCELED = 'canceled', _('canceled')

    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    document = models.ForeignKey(
        Document, db_constraint=False, on_delete=models.DO_NOTHING, db_column='document_id', related_name='doc_lib',
        null=True,
    )
    doc_id = models.BigIntegerField(null=True)
    collection_id = models.CharField(null=True, max_length=36)
    task_type = models.CharField(null=True)
    task_id = models.CharField(null=True, blank=True, max_length=36)
    task_status = models.CharField(
        null=True, blank=True, max_length=32, db_index=True, default=TaskStatusChoices.PENDING)
    error = models.JSONField(null=True)
    filename = models.CharField(null=True, blank=True, max_length=512)
    object_path = models.CharField(null=True, blank=True, max_length=512)
    folder = models.ForeignKey(
        'DocumentLibraryFolder', db_constraint=False, on_delete=models.DO_NOTHING, db_column='folder_id',
        related_name='doc_lib_folder', null=True, default=None
    )
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        index_together = ['collection_id', 'doc_id']
        db_table = 'document_library'
        verbose_name = 'document_library'


class DocumentLibraryFolder(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    name = models.CharField(null=False, blank=False, max_length=200)
    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    bot = models.ForeignKey(
        'bot.Bot', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='bot_id')
    collection = models.ForeignKey(
        'collection.Collection', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='collection_id')
    del_flag = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = 'document_library_folder'
        verbose_name = 'document_library_folder'
