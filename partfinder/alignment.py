"""Loading, Saving, Parsing Alignment Files

    See the phyml details here:
    http://www.atgc-montpellier.fr/phyml/usersguide.php?type=command

"""
import logging
log = logging.getLogger("alignment")

import os

from pyparsing import (
    Word, OneOrMore, alphas, nums, Suppress, Optional, Group, stringEnd,
    delimitedList, ParseException, line, lineno, col, LineStart, restOfLine,
    LineEnd, White, Literal, Combine, Or, MatchFirst)

# TODO: Should really detect which it is...
# alignment_format = 'fasta'
alignment_format = 'phy'

from util import PartitionFinderError
class AlignmentError(PartitionFinderError):
    pass

class AlignmentParser(object):
    """Parses an alignment and returns species sequence tuples"""
    
    # I think this covers it...
    BASES = Word(alphas + "?.-")

    def __init__(self):
        self.sequences = {}
        self.seqlen = None

        # TODO: We should be able to read both of these...!
        if alignment_format == 'phy':
            self.root_parser = self.phylip_parser() + stringEnd
        elif alignment_format == 'fasta':
            self.root_parser = self.fasta_parser() + stringEnd

    def fasta_parser(self):
        # Some syntax that we need, but don't bother looking at
        GREATER = Literal(">")

        sequence_name = Suppress(LineStart() + GREATER) + restOfLine
        sequence_name.setParseAction(lambda toks: "".join(toks))
        sequence_bases = OneOrMore(self.BASES + Suppress(LineEnd()))
        sequence_bases.setParseAction(lambda toks: "".join(toks))

        # Any sequence is the name follow by the bases
        seq = Group(sequence_name("species") + sequence_bases("sequence"))
        sequences = OneOrMore(seq)
        # Main parser: one or more definitions 
        return sequences("sequences")

    def phylip_parser(self):

        INTEGER = Word(nums) 
        INTEGER.setParseAction(lambda x: int(x[0]))

        header = Group(INTEGER("species_count") +
                       INTEGER("sequence_length") + Suppress(restOfLine))

        sequence_name = Word(
            alphas + nums + "!#$%&\'*+-./;<=>?@[\\]^_`{|}~", 
            max=100)


        # Take a copy and disallow line breaks in the bases
        bases = self.BASES.copy()
        bases.setWhitespaceChars(" \t")
        base_chain = OneOrMore(bases)
        base_chain.setParseAction(lambda x: ''.join(x))
        seq = Group(sequence_name("species") + base_chain("sequence")) + Suppress(LineEnd())

        sequences = OneOrMore(seq)
        return header("header") + sequences("sequences")

    def parse(self, s):
        try:
            defs = self.root_parser.parseString(s)
        except ParseException, p:
            log.error("Error in Alignment Parsing:" + str(p))
            raise AlignmentError

        # Not all formats have a heading, but if we have one do some checking
        if defs.header:
            if len(defs.sequences) != defs.header.species_count:
                log.error("Bad Alignment file: species count in header does not match" 
                " number of sequences in file, please check")
                raise AlignmentError

            if len(defs.sequences[0][1]) != defs.header.sequence_length:
                log.error("Bad Alignment file: sequence length count in header does not match"
                " sequence length in file, please check")
                raise AlignmentError

        # Don't make a dictionary yet, as we want to check it for repeats
        return [(x.species, x.sequence) for x in defs.sequences]

# Stateless singleton parser
the_parser = AlignmentParser()
def parse(s):
    return the_parser.parse(s)

class Alignment(object):
    def __init__(self):
        self.species = {}
        self.sequence_len = 0

    def __str__(self):
        return "Alignment(%s species, %s codons)" % self.species, self.sequence_len

    def same_as(self, other):
        return self.sequence_len == other.sequence_len and self.species == other.species

    def from_parser_output(self, defs):
        """A series of species / sequences tuples
        e.g def = ("dog", "GATC"), ("cat", "GATT")
        """
        species = {}
        sequence_len = None
        for spec, seq in defs: 
            # log.debug("Found Sequence for %s: %s...", spec, seq[:20])
            if spec in species:
                log.error("Repeated species name '%s' is repeated "
                          "in alignment", spec)
                raise AlignmentError 

            # Assign it
            species[spec] = seq

            if sequence_len is None:
                sequence_len = len(seq)
            else:
                if len(seq) != sequence_len:
                    log.error("Sequence length of %s "
                              "differs from previous sequences", spec)
                    raise AlignmentError
        log.debug("Found %d species with sequence length %d", 
                  len(species), sequence_len)

        # Overwrite these
        self.species = species
        self.sequence_len = sequence_len

    def read(self, pth):
        if not os.path.exists(pth):
            log.error("Cannot find sequence file '%s'", pth)
            raise AlignmentError

        log.info("Reading alignment file '%s'", pth)
        text = open(pth, 'r').read()
        self.from_parser_output(the_parser.parse(text))

    def write(self, pth):
        if alignment_format == 'phy':
            self.write_phylip(pth)
        elif alignment_format is 'fasta':
            self.write_fasta(pth)
        else:
            log.error("Undefined Alignment Format")
            raise AlignmentError

    def write_fasta(self, pth):
        fd = open(pth, 'w')
        log.debug("Writing fasta file '%s'", pth)
        for species, sequence in self.species.iteritems():
            fd.write(">%s\n" % species)
            fd.write("%s\n" % sequence)

    def write_phylip(self, pth):
        fd = open(pth, 'w')
        log.debug("Writing phylip file '%s'", pth)

        species_count = len(self.species)
        sequence_len = len(iter(self.species.itervalues()).next())

        fd.write("%d %d\n" % (species_count, sequence_len))
        for species, sequence in self.species.iteritems():
            # we use a version of phylip which can have longer species names, up to 100
            shortened = "%s    " %(species[:99])
            fd.write(shortened)
            fd.write(sequence)
            fd.write("\n")

class SubsetAlignment(Alignment):
    """Create an alignment based on some others and a subset definition"""
    def __init__(self, source, subset):
        """create an alignment for this subset"""
        Alignment.__init__(self)

        #let's do a basic check to make sure that the specified sites aren't > alignment length
        site_max = max(subset.columns)
        if site_max>source.sequence_len:
            log.error("Site %d is specified in [partitions], but the alignment only has %d sites. Please check." %(site_max, source.sequence_len)) 
            raise AlignmentError

        # Pull out the columns we need
        for species_name, old_sequence in source.species.iteritems():
            new_sequence = ''.join([old_sequence[i] for i in subset.columns])
            self.species[species_name] = new_sequence

        if not self.species:
            log.error("No species found in %s", self)
            raise AlignmentError

        self.sequence_len = len(self.species.itervalues().next())

class TestAlignment(Alignment):
    """Good for testing stuff"""
    def __init__(self, text):
        Alignment.__init__(self)
        self.from_parser_output(the_parser.parse(text))

